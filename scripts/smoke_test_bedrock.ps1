# Smoke test - Amazon Bedrock Converse API
# Validates BedrockClient connectivity and model access before full deployment.
# Uses the same BedrockClient class as the Lambda Integrator.
#
# Exit codes: 0 = success, 1 = failure

param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$ProjectRoot = Join-Path $ScriptDir ".."
$SrcDir = Join-Path $ProjectRoot "src"

Write-Host ""
Write-Host ("=" * 70)
Write-Host " SMOKE TEST - Amazon Bedrock Converse API"
Write-Host ("=" * 70)
Write-Host ""

# --- Step 1: Validate AWS Credentials ---
Write-Host "--- Step 1: Validating AWS credentials ---"

try {
    $identity = aws sts get-caller-identity --output json 2>&1 | ConvertFrom-Json
    Write-Host "[PASS] AWS credentials valid" -ForegroundColor Green
    Write-Host "       Account: $($identity.Account)"
    Write-Host "       ARN:     $($identity.Arn)"
    Write-Host "       Region:  $($env:AWS_REGION ?? 'us-east-1')"
} catch {
    Write-Host "[FAIL] AWS credentials not configured" -ForegroundColor Red
    Write-Host "       Run 'aws configure' or set AWS environment variables."
    Write-Host "       Error: $_"
    exit 1
}

# --- Step 2: Resolve BEDROCK_MODEL_ID ---
Write-Host ""
Write-Host "--- Step 2: Resolving BEDROCK_MODEL_ID ---"

$modelId = $env:BEDROCK_MODEL_ID
if (-not $modelId) {
    Write-Host "[FAIL] BEDROCK_MODEL_ID environment variable not set" -ForegroundColor Red
    Write-Host "       Set it with: `$env:BEDROCK_MODEL_ID = 'your-model-id'"
    Write-Host "       No default is used - model must be explicitly validated."
    exit 1
}

Write-Host "[PASS] BEDROCK_MODEL_ID = $modelId" -ForegroundColor Green

# --- Step 3: Instantiate BedrockClient ---
Write-Host ""
Write-Host "--- Step 3: Instantiating BedrockClient ---"

$pythonScript = @"
import sys
import os
import time
import uuid
import json

sys.path.insert(0, r'$SrcDir')
os.environ.setdefault('AWS_REGION', os.environ.get('AWS_REGION', 'us-east-1'))

try:
    from shared.bedrock_client import BedrockClient, BedrockConfigurationError, BedrockTransientError, BedrockFatalError, BedrockTimeoutError
except ImportError as e:
    print(json.dumps({'error': f'Import failed: {e}', 'type': 'ImportError'}))
    sys.exit(1)

# Instantiate client
try:
    client = BedrockClient()
except BedrockConfigurationError as e:
    print(json.dumps({'error': str(e), 'type': 'BedrockConfigurationError', 'code': e.error_code}))
    sys.exit(1)

# Generate correlation_id
correlation_id = str(uuid.uuid4())

# Send test question (max 50 chars, Portuguese)
test_question = 'Qual e a capital do Brasil?'

start = time.time()
try:
    response = client.converse(
        user_message=test_question,
        correlation_id=correlation_id,
    )
    latency_ms = (time.time() - start) * 1000

    if not response or not response.strip():
        print(json.dumps({
            'error': 'Empty response from model',
            'type': 'EmptyResponse',
            'latency_ms': round(latency_ms, 1),
            'correlation_id': correlation_id,
        }))
        sys.exit(1)

    print(json.dumps({
        'success': True,
        'response': response[:200],
        'response_length': len(response),
        'latency_ms': round(latency_ms, 1),
        'correlation_id': correlation_id,
        'model_id': client.model_id,
    }))

except BedrockConfigurationError as e:
    print(json.dumps({'error': str(e), 'type': 'BedrockConfigurationError', 'code': e.error_code}))
    sys.exit(1)
except BedrockTimeoutError as e:
    latency_ms = (time.time() - start) * 1000
    print(json.dumps({'error': str(e), 'type': 'BedrockTimeoutError', 'code': e.error_code, 'latency_ms': round(latency_ms, 1), 'correlation_id': correlation_id}))
    sys.exit(1)
except BedrockTransientError as e:
    latency_ms = (time.time() - start) * 1000
    print(json.dumps({'error': str(e), 'type': 'BedrockTransientError', 'code': e.error_code, 'latency_ms': round(latency_ms, 1), 'correlation_id': correlation_id}))
    sys.exit(1)
except BedrockFatalError as e:
    latency_ms = (time.time() - start) * 1000
    print(json.dumps({'error': str(e), 'type': 'BedrockFatalError', 'code': e.error_code, 'latency_ms': round(latency_ms, 1), 'correlation_id': correlation_id}))
    sys.exit(1)
except Exception as e:
    latency_ms = (time.time() - start) * 1000
    print(json.dumps({'error': str(e), 'type': type(e).__name__, 'latency_ms': round(latency_ms, 1), 'correlation_id': correlation_id}))
    sys.exit(1)
"@

$env:PYTHONPATH = $SrcDir
$result = py -c $pythonScript 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] BedrockClient call failed" -ForegroundColor Red
    try {
        $parsed = $result | ConvertFrom-Json
        Write-Host "       Error type: $($parsed.type)" -ForegroundColor Yellow
        Write-Host "       Error:      $($parsed.error)" -ForegroundColor Yellow
        if ($parsed.code) { Write-Host "       Code:       $($parsed.code)" -ForegroundColor Yellow }
        if ($parsed.latency_ms) { Write-Host "       Latency:    $($parsed.latency_ms) ms" }
        if ($parsed.correlation_id) { Write-Host "       Corr ID:    $($parsed.correlation_id)" }
    } catch {
        Write-Host "       Raw output: $result" -ForegroundColor Yellow
    }
    exit 1
}

# --- Step 4: Validate response ---
Write-Host ""
Write-Host "--- Step 4: Validating response ---"

try {
    $parsed = $result | ConvertFrom-Json
} catch {
    Write-Host "[FAIL] Could not parse response as JSON" -ForegroundColor Red
    Write-Host "       Raw: $result"
    exit 1
}

if ($parsed.success) {
    Write-Host "[PASS] Bedrock responded successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Model:          $($parsed.model_id)"
    Write-Host "  Latency:        $($parsed.latency_ms) ms"
    Write-Host "  Response length: $($parsed.response_length) chars"
    Write-Host "  Correlation ID: $($parsed.correlation_id)"
    Write-Host ""
    Write-Host "  Response (first 200 chars):"
    Write-Host "  $($parsed.response)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host ("=" * 70)
    Write-Host " SMOKE TEST PASSED" -ForegroundColor Green
    Write-Host ("=" * 70)
    exit 0
} else {
    Write-Host "[FAIL] Unexpected response format" -ForegroundColor Red
    Write-Host "       $result"
    exit 1
}
