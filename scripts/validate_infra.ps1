<#
.SYNOPSIS
    Valida se a infraestrutura AWS da POC Bedrock está de pé antes de usar a app.

.DESCRIPTION
    Verifica: credenciais, Lambdas, SNS, SQS, DynamoDB, KMS, modelo Bedrock.
    Execute antes de testar o widget ou rodar smoke tests.

.EXAMPLE
    powershell -File scripts/validate_infra.ps1
#>

$ErrorActionPreference = "Continue"
$Region = "us-east-1"
$Profile = "connect-poc"
$Prefix = "connect-bedrock-poc-dev"

$passed = 0
$failed = 0
$warnings = 0

function Write-Check {
    param([string]$Name, [string]$Status, [string]$Detail)
    switch ($Status) {
        "OK"   { Write-Host "  [OK] $Name" -ForegroundColor Green; $script:passed++ }
        "FAIL" { Write-Host "  [FAIL] $Name - $Detail" -ForegroundColor Red; $script:failed++ }
        "WARN" { Write-Host "  [WARN] $Name - $Detail" -ForegroundColor Yellow; $script:warnings++ }
    }
}

Write-Host ""
Write-Host "=" * 60
Write-Host "  POC Bedrock - Validacao de Infraestrutura"
Write-Host "=" * 60
Write-Host ""

# 1. Credenciais AWS
Write-Host "[1/8] Credenciais AWS" -ForegroundColor Cyan
try {
    $identity = aws sts get-caller-identity --profile $Profile --region $Region --output json 2>&1 | ConvertFrom-Json
    if ($identity.Account) {
        Write-Check "AWS Profile '$Profile'" "OK"
        Write-Check "Account: $($identity.Account)" "OK"
    } else {
        Write-Check "AWS Credentials" "FAIL" "Nao foi possivel obter identidade"
    }
} catch {
    Write-Check "AWS Credentials" "FAIL" "Erro: $_"
}

# 2. Lambda Initializer
Write-Host ""
Write-Host "[2/8] Lambda Initializer" -ForegroundColor Cyan
$initLambda = aws lambda get-function --function-name "$Prefix-initializer" --region $Region --profile $Profile --output json 2>&1
if ($initLambda -match "ResourceNotFoundException") {
    Write-Check "Lambda $Prefix-initializer" "FAIL" "Nao existe (foi excluida)"
} elseif ($initLambda -match "error" -or $initLambda -match "Error") {
    Write-Check "Lambda $Prefix-initializer" "FAIL" "$initLambda"
} else {
    $initData = $initLambda | ConvertFrom-Json
    Write-Check "Lambda $Prefix-initializer" "OK"
    Write-Check "  State: $($initData.Configuration.State)" "OK"
}

# 3. Lambda Integrator
Write-Host ""
Write-Host "[3/8] Lambda Integrator" -ForegroundColor Cyan
$intLambda = aws lambda get-function --function-name "$Prefix-integrator" --region $Region --profile $Profile --output json 2>&1
if ($intLambda -match "ResourceNotFoundException") {
    Write-Check "Lambda $Prefix-integrator" "FAIL" "Nao existe (foi excluida)"
} elseif ($intLambda -match "error" -or $intLambda -match "Error") {
    Write-Check "Lambda $Prefix-integrator" "FAIL" "$intLambda"
} else {
    $intData = $intLambda | ConvertFrom-Json
    Write-Check "Lambda $Prefix-integrator" "OK"
    Write-Check "  State: $($intData.Configuration.State)" "OK"
}

# 4. SNS Topic
Write-Host ""
Write-Host "[4/8] SNS Topic" -ForegroundColor Cyan
$topics = aws sns list-topics --region $Region --profile $Profile --output json 2>&1 | ConvertFrom-Json
$pocTopic = $topics.Topics | Where-Object { $_.TopicArn -match "connect-bedrock-poc" }
if ($pocTopic) {
    Write-Check "SNS Topic" "OK"
    Write-Check "  ARN: $($pocTopic.TopicArn)" "OK"
} else {
    Write-Check "SNS Topic (connect-bedrock-poc*)" "FAIL" "Nenhum topico encontrado"
}

# 5. SQS Queues
Write-Host ""
Write-Host "[5/8] SQS Queues" -ForegroundColor Cyan
$queues = aws sqs list-queues --region $Region --profile $Profile --queue-name-prefix connect-bedrock-poc --output json 2>&1 | ConvertFrom-Json
if ($queues.QueueUrls -and $queues.QueueUrls.Count -gt 0) {
    foreach ($q in $queues.QueueUrls) {
        $qName = $q.Split("/")[-1]
        Write-Check "SQS: $qName" "OK"
    }
} else {
    Write-Check "SQS Queues (connect-bedrock-poc*)" "FAIL" "Nenhuma fila encontrada"
}

# 6. DynamoDB Tables
Write-Host ""
Write-Host "[6/8] DynamoDB Tables" -ForegroundColor Cyan
$tables = aws dynamodb list-tables --region $Region --profile $Profile --output json 2>&1 | ConvertFrom-Json
$pocTables = $tables.TableNames | Where-Object { $_ -match "connect-bedrock-poc" }
if ($pocTables -and $pocTables.Count -gt 0) {
    foreach ($t in $pocTables) {
        Write-Check "DynamoDB: $t" "OK"
    }
} else {
    Write-Check "DynamoDB Tables (connect-bedrock-poc*)" "FAIL" "Nenhuma tabela encontrada"
}

# 7. KMS Key
Write-Host ""
Write-Host "[7/8] KMS Key" -ForegroundColor Cyan
$aliases = aws kms list-aliases --region $Region --profile $Profile --output json 2>&1 | ConvertFrom-Json
$pocKey = $aliases.Aliases | Where-Object { $_.AliasName -match "connect-bedrock-poc" }
if ($pocKey) {
    Write-Check "KMS Key: $($pocKey.AliasName)" "OK"
} else {
    Write-Check "KMS Key (connect-bedrock-poc*)" "WARN" "Nenhum alias encontrado (pode usar aws/dynamodb)"
}

# 8. Bedrock Model Access
Write-Host ""
Write-Host "[8/8] Bedrock Model Access" -ForegroundColor Cyan
$modelTest = aws bedrock get-foundation-model --model-identifier "amazon.nova-micro-v1:0" --region $Region --profile $Profile --output json 2>&1
if ($modelTest -match "error" -or $modelTest -match "Error") {
    Write-Check "Bedrock Model (amazon.nova-micro-v1:0)" "WARN" "Nao foi possivel verificar acesso"
} else {
    Write-Check "Bedrock Model (amazon.nova-micro-v1:0)" "OK"
}

# Resultado final
Write-Host ""
Write-Host "=" * 60
Write-Host "  RESULTADO" -ForegroundColor Cyan
Write-Host "  Passou: $passed | Falhou: $failed | Avisos: $warnings"
if ($failed -gt 0) {
    Write-Host ""
    Write-Host "  INFRAESTRUTURA INCOMPLETA" -ForegroundColor Red
    Write-Host "  A app nao vai funcionar. Execute:" -ForegroundColor Red
    Write-Host "    1. powershell -File scripts/build_lambdas.ps1" -ForegroundColor Yellow
    Write-Host "    2. cd terraform; `$env:AWS_PROFILE='connect-poc'; terraform init; terraform plan" -ForegroundColor Yellow
    Write-Host "    3. terraform apply (com autorizacao)" -ForegroundColor Yellow
    Write-Host ""
    exit 1
} else {
    Write-Host ""
    Write-Host "  INFRAESTRUTURA OK - App pronta para uso" -ForegroundColor Green
    Write-Host ""
    exit 0
}
