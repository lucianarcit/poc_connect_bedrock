# Pre-plan validation script
# Runs mandatory checks before any terraform plan/apply.

param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$FORBIDDEN_PATTERN = "connect-mcp-poc"
$EXPECTED_PREFIX = "connect-bedrock-poc"
$TerraformDir = Join-Path (Join-Path $PSScriptRoot "..") "terraform"
$FailCount = 0

function Write-Check {
    param([string]$Name, [bool]$Passed, [string]$Detail = "")
    if ($Passed) {
        Write-Host "[PASS] $Name" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Name" -ForegroundColor Red
        if ($Detail) { Write-Host "       $Detail" -ForegroundColor Yellow }
        $script:FailCount++
    }
}

Write-Host ""
Write-Host ("=" * 70)
Write-Host " PRE-PLAN VALIDATION - MCP POC Impact Protection"
Write-Host ("=" * 70)
Write-Host ""

# --- Check 1: No .tfstate with MCP references ---
Write-Host "--- Check 1: Terraform State ---"

$stateFiles = Get-ChildItem -Path $TerraformDir -Filter "*.tfstate" -Recurse -ErrorAction SilentlyContinue
$stateContaminated = $false

foreach ($file in $stateFiles) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    if ($content -and $content.Contains($FORBIDDEN_PATTERN)) {
        $stateContaminated = $true
        Write-Check -Name "State file free of MCP references" -Passed $false `
            -Detail "Found MCP reference in $($file.FullName)"
    }
}

if (-not $stateContaminated) {
    Write-Check -Name "No .tfstate contaminated with MCP references" -Passed $true
}

# --- Check 2: Backend not pointing to MCP ---
Write-Host ""
Write-Host "--- Check 2: Backend ---"

$backendFiles = @("providers.tf", "terraform.tf", "backend.tf") |
    ForEach-Object { Join-Path $TerraformDir $_ } |
    Where-Object { Test-Path $_ }

$backendContaminated = $false
foreach ($file in $backendFiles) {
    $content = Get-Content $file -Raw -ErrorAction SilentlyContinue
    if ($content -and $content.Contains($FORBIDDEN_PATTERN)) {
        $backendContaminated = $true
        $fileName = [System.IO.Path]::GetFileName($file)
        Write-Check -Name "Backend in $fileName free of MCP" -Passed $false `
            -Detail "Found MCP reference"
    }
}

if (-not $backendContaminated) {
    Write-Check -Name "Backend config free of MCP references" -Passed $true
}

# --- Check 3: Prefix in locals.tf ---
Write-Host ""
Write-Host "--- Check 3: Resource Prefix ---"

$localsFile = Join-Path $TerraformDir "locals.tf"
if (Test-Path $localsFile) {
    $localsContent = Get-Content $localsFile -Raw
    $pattern = 'prefix\s*=\s*"([^"]+)"'
    $prefixMatch = [regex]::Match($localsContent, $pattern)

    if ($prefixMatch.Success) {
        $currentPrefix = $prefixMatch.Groups[1].Value
        $prefixCorrect = $currentPrefix -eq $EXPECTED_PREFIX

        Write-Check -Name "locals.prefix = $EXPECTED_PREFIX" -Passed $prefixCorrect `
            -Detail "Current value: $currentPrefix"
    } else {
        Write-Check -Name "locals.prefix defined" -Passed $false `
            -Detail "Could not find prefix definition in locals.tf"
    }
} else {
    Write-Check -Name "locals.tf exists" -Passed $false `
        -Detail "File $localsFile not found"
}

# --- Check 4: No active MCP references in .tf files ---
Write-Host ""
Write-Host "--- Check 4: .tf files without MCP references ---"

$tfFiles = Get-ChildItem -Path $TerraformDir -Filter "*.tf" -ErrorAction SilentlyContinue
$mcpReferences = @()

foreach ($file in $tfFiles) {
    $lines = Get-Content $file.FullName -ErrorAction SilentlyContinue
    if (-not $lines) { continue }
    $lineNum = 0
    foreach ($line in $lines) {
        $lineNum++
        $trimmed = $line.TrimStart()
        # Skip comments
        if ($trimmed.StartsWith("#") -or $trimmed.StartsWith("//")) { continue }
        if ($line.Contains($FORBIDDEN_PATTERN)) {
            $mcpReferences += "$($file.Name):$lineNum - $($line.Trim())"
        }
    }
}

if ($mcpReferences.Count -eq 0) {
    Write-Check -Name "No active MCP references in .tf files" -Passed $true
} else {
    Write-Check -Name ".tf files free of active MCP references" -Passed $false `
        -Detail "Found $($mcpReferences.Count) reference(s)"
    foreach ($ref in $mcpReferences) {
        Write-Host "       - $ref" -ForegroundColor Yellow
    }
}

# --- Final Result ---
Write-Host ""
Write-Host ("=" * 70)

if ($FailCount -eq 0) {
    Write-Host " RESULT: ALL CHECKS PASSED" -ForegroundColor Green
    Write-Host " Safe to run: terraform plan" -ForegroundColor Green
    Write-Host ("=" * 70)
    exit 0
} else {
    Write-Host " RESULT: $FailCount CHECK(S) FAILED" -ForegroundColor Red
    Write-Host " ABORT: Do NOT run terraform plan until issues above are resolved." -ForegroundColor Red
    Write-Host ("=" * 70)
    exit 1
}
