# smoke_test_mcp.ps1 — Teste de fumaça do MCP Server via Lambda Function URL real.
#
# Executa o protocolo MCP completo contra a infraestrutura AWS publicada:
#   1. Lê MCP_SERVER_URL da configuração remota da Lambda Integrator
#   2. Assina cada request com SigV4
#   3. Executa: initialize → notifications/initialized → tools/list → tools/call
#   4. Exibe diagnóstico detalhado de cada etapa
#   5. Em caso de falha, consulta logs do MCP Server
#
# Requer:
#   - AWS CLI v2 configurado (profile ou env vars)
#   - Python 3.12+ com boto3 e httpx instalados
#   - Infraestrutura já deployada (terraform apply concluído)
#
# Uso:
#   .\scripts\smoke_test_mcp.ps1
#   .\scripts\smoke_test_mcp.ps1 -Profile connect-poc -Region us-east-1
#
# Exit codes:
#   0 = sucesso
#   1 = falha em alguma etapa

param(
    [string]$Profile = "connect-poc",
    [string]$Region = "us-east-1",
    [string]$FunctionName = "connect-mcp-poc-dev-integrator",
    [string]$McpFunctionName = "connect-mcp-poc-dev-mcp-server"
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "=== MCP Server Smoke Test ===" -ForegroundColor Cyan
Write-Host ""

# Step 0: Validate AWS identity
Write-Host "[0] Validating AWS identity..." -ForegroundColor Yellow
$identity = aws sts get-caller-identity --profile $Profile --region $Region --output json 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: AWS credentials invalid" -ForegroundColor Red
    Write-Host $identity
    exit 1
}
$identityObj = $identity | ConvertFrom-Json
Write-Host "  Account: $($identityObj.Account)"
Write-Host "  Region:  $Region"
Write-Host "  Profile: $Profile"
Write-Host ""

# Step 1: Get MCP_SERVER_URL from Lambda configuration
Write-Host "[1] Reading MCP_SERVER_URL from Lambda $FunctionName..." -ForegroundColor Yellow
$lambdaConfig = aws lambda get-function-configuration `
    --function-name $FunctionName `
    --profile $Profile `
    --region $Region `
    --output json 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: Cannot read Lambda config" -ForegroundColor Red
    Write-Host $lambdaConfig
    exit 1
}

$configObj = $lambdaConfig | ConvertFrom-Json
$mcpUrl = $configObj.Environment.Variables.MCP_SERVER_URL
$lastModifiedIntegrator = $configObj.LastModified

Write-Host "  MCP_SERVER_URL: [$mcpUrl]"
Write-Host "  URL length: $($mcpUrl.Length)"
Write-Host "  Ends with /: $($mcpUrl.EndsWith('/'))"
Write-Host "  Integrator LastModified: $lastModifiedIntegrator"

if (-not $mcpUrl) {
    Write-Host "FAIL: MCP_SERVER_URL not found in Lambda env vars" -ForegroundColor Red
    exit 1
}

# Get MCP Server Lambda info
$mcpConfig = aws lambda get-function-configuration `
    --function-name $McpFunctionName `
    --profile $Profile `
    --region $Region `
    --output json 2>&1 | ConvertFrom-Json

Write-Host "  MCP Server LastModified: $($mcpConfig.LastModified)"
Write-Host "  MCP Server CodeSha256:   $($mcpConfig.CodeSha256.Substring(0,16))..."
Write-Host ""

# Step 2: Execute MCP protocol via Python (SigV4 signing)
Write-Host "[2] Executing MCP protocol against $mcpUrl" -ForegroundColor Yellow
Write-Host ""

$pythonScript = @"
import sys, json, time, uuid, os

# Configurar AWS profile
os.environ.setdefault("AWS_PROFILE", "$Profile")
os.environ.setdefault("AWS_DEFAULT_REGION", "$Region")

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session
import httpx

MCP_URL = "$mcpUrl"
REGION = "$Region"
CORRELATION_ID = f"smoke-{uuid.uuid4().hex[:8]}"

print(f"  PYTHON MCP_URL repr={MCP_URL!r}", flush=True)
print(f"  PYTHON MCP_URL endswith /: {MCP_URL.endswith('/')}", flush=True)
print(f"  PYTHON MCP_URL length: {len(MCP_URL)}", flush=True)
print(f"  Correlation ID: {CORRELATION_ID}")
print(f"  Target URL:     {MCP_URL}")
print()

session = Session()
session.set_config_variable("profile", "$Profile")
credentials = session.get_credentials().get_frozen_credentials()

def sign_and_post(url, payload_dict, session_id=None):
    body = json.dumps(payload_dict).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "X-Correlation-Id": CORRELATION_ID,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    print(f"  SIGN_AND_POST url repr={url!r}", flush=True)

    aws_request = AWSRequest(method="POST", url=url, headers=headers, data=body)
    signer = SigV4Auth(credentials, "lambda", REGION)
    signer.add_auth(aws_request)

    print(f"  AFTER_SIGN aws_request.url={aws_request.url!r}", flush=True)

    # Check httpx request URL before sending
    import httpx as _httpx
    check_req = _httpx.Request("POST", url, content=body, headers=dict(aws_request.headers))
    print(f"  HTTPX_REQUEST url={str(check_req.url)!r} path={check_req.url.raw_path!r}", flush=True)

    start = time.time()
    with httpx.Client(timeout=15.0, follow_redirects=False) as client:
        response = client.post(url, content=body, headers=dict(aws_request.headers))
    duration_ms = int((time.time() - start) * 1000)

    print(f"  RESPONSE url={str(response.url)!r} status={response.status_code}", flush=True)

    return response, duration_ms

def print_step(name, response, duration_ms):
    ct = response.headers.get("content-type", "")
    loc = response.headers.get("location", "")
    sid = response.headers.get("mcp-session-id", "")
    body_preview = response.text[:150] if response.text else "(empty)"

    print(f"  [{name}]")
    print(f"    URL:          {MCP_URL}")
    print(f"    Status:       {response.status_code}")
    print(f"    Content-Type: {ct}")
    if loc:
        print(f"    Location:     {loc}")
    if sid:
        print(f"    Session-Id:   {sid[:20]}...")
    print(f"    Body preview: {body_preview}")
    print(f"    Duration:     {duration_ms}ms")
    print()
    return sid

def fail(msg):
    print(f"  FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

# --- Step 2a: initialize ---
init_payload = {
    "jsonrpc": "2.0",
    "id": str(uuid.uuid4()),
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "smoke-test", "version": "1.0", "correlationId": CORRELATION_ID},
    },
}

resp, ms = sign_and_post(MCP_URL, init_payload)
session_id = print_step("initialize", resp, ms)

if resp.status_code != 200:
    fail(f"initialize returned {resp.status_code}, expected 200. Body: {resp.text[:200]}")

if not session_id:
    session_id = resp.headers.get("mcp-session-id", "")

try:
    init_result = resp.json()
    if "error" in init_result:
        fail(f"initialize JSON-RPC error: {init_result['error']}")
    if "result" not in init_result:
        fail(f"initialize missing 'result': {json.dumps(init_result)[:200]}")
except Exception as e:
    fail(f"initialize response not JSON: {e}")

# --- Step 2b: notifications/initialized ---
notif_payload = {
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
}

resp, ms = sign_and_post(MCP_URL, notif_payload, session_id)
print_step("notifications/initialized", resp, ms)

if resp.status_code not in (200, 202, 204):
    fail(f"notifications/initialized returned {resp.status_code}, expected 200/202/204")

# --- Step 2c: tools/list ---
list_payload = {
    "jsonrpc": "2.0",
    "id": str(uuid.uuid4()),
    "method": "tools/list",
    "params": {},
}

resp, ms = sign_and_post(MCP_URL, list_payload, session_id)
print_step("tools/list", resp, ms)

if resp.status_code != 200:
    fail(f"tools/list returned {resp.status_code}")

try:
    list_result = resp.json()
    tools = list_result.get("result", {}).get("tools", [])
    tool_names = [t["name"] for t in tools]
    print(f"    Tools found: {tool_names}")
    print()
    if "search_support_documentation" not in tool_names:
        fail(f"search_support_documentation not in tools: {tool_names}")
except Exception as e:
    fail(f"tools/list parse error: {e}")

# --- Step 2d: tools/call ---
call_payload = {
    "jsonrpc": "2.0",
    "id": str(uuid.uuid4()),
    "method": "tools/call",
    "params": {
        "name": "search_support_documentation",
        "arguments": {"question": "como trocar senha", "product": "", "language": "pt-BR"},
    },
}

resp, ms = sign_and_post(MCP_URL, call_payload, session_id)
print_step("tools/call", resp, ms)

if resp.status_code != 200:
    fail(f"tools/call returned {resp.status_code}")

try:
    call_result = resp.json()
    if "error" in call_result:
        fail(f"tools/call JSON-RPC error: {call_result['error']}")
    content = call_result.get("result", {}).get("content", [])
    if not content:
        fail("tools/call returned empty content")
    text = content[0].get("text", "")
    parsed = json.loads(text)
    print(f"    Tool result keys: {list(parsed.keys())}")
    if "answer" in parsed:
        print(f"    Answer preview:   {parsed['answer'][:80]}...")
    print()
except Exception as e:
    fail(f"tools/call parse error: {e}")

print("=== ALL STEPS PASSED ===")
print(f"  Correlation ID: {CORRELATION_ID}")
print(f"  Use this to search logs:")
print(f"    aws logs filter-log-events --log-group-name /aws/lambda/$McpFunctionName --filter-pattern \"{CORRELATION_ID}\" --region $Region --profile $Profile")
"@

$result = echo $pythonScript | C:\proj\poc_connect\.venv\Scripts\python.exe - 2>&1
$exitCode = $LASTEXITCODE

# Display output
$result | ForEach-Object { Write-Host $_ }

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "=== SMOKE TEST FAILED ===" -ForegroundColor Red
    Write-Host ""
    Write-Host "[3] Fetching MCP Server logs..." -ForegroundColor Yellow

    $endTime = [int][double]::Parse((Get-Date -UFormat %s)) * 1000
    $startTime = $endTime - 60000  # last 60 seconds

    $logs = aws logs filter-log-events `
        --log-group-name "/aws/lambda/$McpFunctionName" `
        --start-time $startTime `
        --end-time $endTime `
        --profile $Profile `
        --region $Region `
        --query "events[].message" `
        --output text 2>&1

    if ($logs) {
        Write-Host "  Recent MCP Server logs:" -ForegroundColor Yellow
        $logs | Select-Object -First 20 | ForEach-Object { Write-Host "    $_" }
    } else {
        Write-Host "  No recent logs found in /aws/lambda/$McpFunctionName" -ForegroundColor Yellow
    }

    exit 1
}

Write-Host ""
Write-Host "=== SMOKE TEST PASSED ===" -ForegroundColor Green
exit 0
