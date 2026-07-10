<#
.SYNOPSIS
    Inicia o servidor local e abre o widget de teste no navegador.

.EXAMPLE
    powershell -File scripts/start_app.ps1
#>

$ErrorActionPreference = "Stop"
$Port = 8080
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DemoDir = Join-Path $ProjectRoot "demo"
$Url = "http://localhost:$Port/connect-bedrock-widget-test.html"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  POC Bedrock - Iniciando app local"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Porta: $Port"
Write-Host "  URL:   $Url"
Write-Host ""

# Verificar se a porta já está em uso
$portInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "  Porta $Port ja em uso. Abrindo navegador direto..." -ForegroundColor Yellow
    Start-Process $Url
    exit 0
}

# Abrir navegador após 2 segundos (em background)
$job = Start-Job -ScriptBlock {
    param($url)
    Start-Sleep -Seconds 2
    Start-Process $url
} -ArgumentList $Url

Write-Host "  Servidor iniciando... (Ctrl+C para parar)" -ForegroundColor Green
Write-Host ""

# Iniciar servidor HTTP
try {
    Push-Location $DemoDir
    python -m http.server $Port --bind 127.0.0.1
} finally {
    Pop-Location
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -ErrorAction SilentlyContinue
}
