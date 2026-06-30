# diagnose_mcp.ps1 — Diagnóstico completo do MCP Server deployado.
#
# 1. Testa / , /mcp , /mcp/ via Function URL com SigV4
# 2. Invoca diretamente a Lambda com evento Function URL v2
# 3. Compara hashes do artefato local vs remoto
# 4. Extrai e inspeciona o ZIP publicado
# 5. Consulta logs recentes
#
# Uso: .\scripts\diagnose_mcp.ps1 -Profile connect-poc -Region us-east-1

param(
    [string]$Profile = "connect-poc",
    [string]$Region = "us-east-1",
    [string]$McpFunctionName = "connect-mcp-poc-dev-mcp-server",
    [string]$IntegratorFunctionName = "connect-mcp-poc-dev-integrator"
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "=== MCP Server Diagnostic ===" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Get Function URL and Lambda config ---
Write-Host "[1] Lambda configuration" -ForegroundColor Yellow

$mcpConfig = aws lambda get-function-configuration `
    --function-name $McpFunctionName `
    --profile $Profile --region $Region --output json | ConvertFrom-Json

Write-Host "  Handler:          $($mcpConfig.Handler)"
Write-Host "  Runtime:          $($mcpConfig.Runtime)"
Write-Host "  Architectures:    $($mcpConfig.Architectures -join ', ')"
Write-Host "  LastModified:     $($mcpConfig.LastModified)"
Write-Host "  LastUpdateStatus: $($mcpConfig.LastUpdateStatus)"
Write-Host "  CodeSha256:       $($mcpConfig.CodeSha256)"
Write-Host "  CodeSize:         $($mcpConfig.CodeSize) bytes"
Write-Host ""

$urlConfig = aws lambda get-function-url-config `
    --function-name $McpFunctionName `
    --profile $Profile --region $Region --output json | ConvertFrom-Json

$functionUrl = $urlConfig.FunctionUrl
Write-Host "  Function URL:     $functionUrl"
Write-Host "  Auth Type:        $($urlConfig.AuthType)"
Write-Host ""

# Get MCP_SERVER_URL from integrator
$intConfig = aws lambda get-function-configuration `
    --function-name $IntegratorFunctionName `
    --profile $Profile --region $Region --output json | ConvertFrom-Json
$mcpServerUrl = $intConfig.Environment.Variables.MCP_SERVER_URL
Write-Host "  Integrator MCP_SERVER_URL: $mcpServerUrl"
Write-Host ""

# --- Step 2: Compare local ZIP hash vs remote ---
Write-Host "[2] Artifact comparison" -ForegroundColor Yellow

$localZip = Join-Path $ROOT "packages\mcp_server.zip"
if (Test-Path $localZip) {
    $localHash = (Get-FileHash $localZip -Algorithm SHA256).Hash
    # AWS uses base64 SHA256
    $localBytes = [System.IO.File]::ReadAllBytes($localZip)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $hashBytes = $sha256.ComputeHash($localBytes)
    $localBase64 = [System.Convert]::ToBase64String($hashBytes)

    Write-Host "  Local ZIP:        $localZip"
    Write-Host "  Local size:       $((Get-Item $localZip).Length) bytes"
    Write-Host "  Local SHA256 b64: $localBase64"
    Write-Host "  Remote CodeSha256: $($mcpConfig.CodeSha256)"

    if ($localBase64 -eq $mcpConfig.CodeSha256) {
        Write-Host "  MATCH: Local ZIP = deployed Lambda" -ForegroundColor Green
    } else {
        Write-Host "  MISMATCH: Local ZIP differs from deployed Lambda!" -ForegroundColor Red
        Write-Host "  The deployed Lambda has DIFFERENT code than the local ZIP."
    }
} else {
    Write-Host "  Local ZIP not found at $localZip"
    Write-Host "  Run: .\scripts\build_lambdas.ps1 -Function mcp_server"
}
Write-Host ""

# --- Step 3: Inspect local ZIP contents ---
Write-Host "[3] Local ZIP inspection" -ForegroundColor Yellow

if (Test-Path $localZip) {
    $inspectScript = @"
import zipfile, sys
zf = zipfile.ZipFile(sys.argv[1])
names = zf.namelist()

# Check key files
key_files = ['mcp_server/handler.py', 'mcp_server/server.py']
for f in key_files:
    present = f in names
    print(f"  {f}: {'PRESENT' if present else 'MISSING'}")

# Extract and check handler content
if 'mcp_server/handler.py' in names:
    content = zf.read('mcp_server/handler.py').decode()
    checks = {
        'redirect_slashes = False': 'redirect_slashes = False' in content or 'redirect_slashes=False' in content,
        'lifespan="on"': 'lifespan="on"' in content or "lifespan='on'" in content,
    }
    print()
    print("  handler.py checks:")
    for check, found in checks.items():
        status = 'FOUND' if found else 'NOT FOUND'
        print(f"    {check}: {status}")

if 'mcp_server/server.py' in names:
    content = zf.read('mcp_server/server.py').decode()
    checks = {
        'enable_dns_rebinding_protection=False': 'enable_dns_rebinding_protection=False' in content or 'enable_dns_rebinding_protection = False' in content,
        'from __future__ import annotations ABSENT': 'from __future__ import annotations' not in content,
    }
    print()
    print("  server.py checks:")
    for check, found in checks.items():
        status = 'FOUND/OK' if found else 'NOT FOUND/PROBLEM'
        print(f"    {check}: {status}")
"@
    echo $inspectScript | python - $localZip
}
Write-Host ""

# --- Step 4: Test paths via Function URL with SigV4 ---
Write-Host "[4] Path testing via Function URL (SigV4)" -ForegroundColor Yellow

$pathTestScript = @"
import sys, json, os, time
os.environ.setdefault("AWS_PROFILE", "$Profile")
os.environ.setdefault("AWS_DEFAULT_REGION", "$Region")

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session
import httpx

FUNCTION_URL = "$functionUrl"
REGION = "$Region"

session = Session()
session.set_config_variable("profile", "$Profile")
credentials = session.get_credentials().get_frozen_credentials()

body = json.dumps({"jsonrpc": "2.0", "id": "diag-1", "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
               "clientInfo": {"name": "diag", "version": "1"}}}).encode()

print()
print("  Path        Status  Location                Content-Type         Body preview")
print("  ----------  ------  ----------------------  -------------------  ------------")

for path in ["/", "/mcp", "/mcp/"]:
    url = FUNCTION_URL.rstrip("/") + path
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    aws_req = AWSRequest(method="POST", url=url, headers=headers, data=body)
    SigV4Auth(credentials, "lambda", REGION).add_auth(aws_req)

    with httpx.Client(timeout=10.0, follow_redirects=False) as c:
        resp = c.post(url, content=body, headers=dict(aws_req.headers))

    loc = resp.headers.get("location", "")[:22]
    ct = resp.headers.get("content-type", "")[:19]
    preview = resp.text[:40].replace("\n", " ") if resp.text else "(empty)"
    print(f"  {path:<10}  {resp.status_code:<6}  {loc:<22}  {ct:<19}  {preview}")

print()
"@
echo $pathTestScript | python -
Write-Host ""

# --- Step 5: Direct Lambda invoke (bypass Function URL) ---
Write-Host "[5] Direct Lambda invoke (aws lambda invoke)" -ForegroundColor Yellow

$invokePayload = @{
    version = "2.0"
    routeKey = "`$default"
    rawPath = "/mcp"
    rawQueryString = ""
    headers = @{
        "content-type" = "application/json"
        "accept" = "application/json, text/event-stream"
        "host" = "direct-invoke.local"
        "x-forwarded-proto" = "https"
    }
    requestContext = @{
        accountId = "123456789012"
        apiId = "direct"
        domainName = "direct-invoke.local"
        domainPrefix = "direct"
        http = @{
            method = "POST"
            path = "/mcp"
            protocol = "HTTP/1.1"
            sourceIp = "127.0.0.1"
            userAgent = "diagnose-script"
        }
        requestId = "diag-req-1"
        routeKey = "`$default"
        stage = "`$default"
        time = "01/Jan/2025:00:00:00 +0000"
        timeEpoch = 1735689600000
    }
    body = '{"jsonrpc":"2.0","id":"diag-direct","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"diag","version":"1"}}}'
    isBase64Encoded = $false
} | ConvertTo-Json -Depth 10 -Compress

$payloadFile = Join-Path $env:TEMP "mcp_invoke_payload.json"
$responseFile = Join-Path $env:TEMP "mcp_invoke_response.json"
$invokePayload | Set-Content -Path $payloadFile -Encoding utf8

aws lambda invoke `
    --function-name $McpFunctionName `
    --payload "fileb://$payloadFile" `
    --profile $Profile `
    --region $Region `
    --cli-binary-format raw-in-base64-out `
    $responseFile 2>&1 | ForEach-Object { Write-Host "  $_" }

if (Test-Path $responseFile) {
    $responseContent = Get-Content $responseFile -Raw | ConvertFrom-Json
    Write-Host ""
    Write-Host "  Direct invoke result:"
    Write-Host "    statusCode: $($responseContent.statusCode)"
    Write-Host "    headers:    $($responseContent.headers | ConvertTo-Json -Compress)"
    $bodyPreview = if ($responseContent.body) { $responseContent.body.Substring(0, [Math]::Min(200, $responseContent.body.Length)) } else { "(empty)" }
    Write-Host "    body:       $bodyPreview"
    Remove-Item $responseFile -ErrorAction SilentlyContinue
}
Remove-Item $payloadFile -ErrorAction SilentlyContinue
Write-Host ""

# --- Step 6: Recent logs ---
Write-Host "[6] Recent MCP Server logs (last 2 minutes)" -ForegroundColor Yellow

$logs = aws logs filter-log-events `
    --log-group-name "/aws/lambda/$McpFunctionName" `
    --start-time ([int]((Get-Date).AddMinutes(-2).ToUniversalTime() - [datetime]'1970-01-01').TotalMilliseconds) `
    --limit 15 `
    --profile $Profile --region $Region `
    --query "events[].message" --output text 2>&1

if ($logs -and $logs -ne "") {
    $logs -split "`n" | Select-Object -First 15 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "  (no logs found)"
}

Write-Host ""
Write-Host "=== Diagnostic complete ===" -ForegroundColor Cyan
