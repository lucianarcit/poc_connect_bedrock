# Checklist Pré-Plan — Proteção contra Impacto na POC MCP

## Objetivo

Este documento define as verificações **obrigatórias** que devem ser executadas antes de qualquer
`terraform plan` ou `terraform apply` neste repositório. O objetivo é garantir isolamento total
entre a POC Bedrock Converse e a POC MCP existente, prevenindo destruição acidental de recursos
em produção da POC MCP.

**Regra absoluta:** Qualquer menção a `connect-mcp-poc` no output de um `terraform plan` invalida
o plan e **DEVE** abortar a operação imediatamente.

---

## Checklist de Verificação

### 1. Estado Terraform (.tfstate)

- [ ] **Nenhum `.tfstate` copiado da POC MCP está presente no diretório `terraform/`**
- [ ] Se existir `terraform/terraform.tfstate`, confirmar que NÃO contém referências a `connect-mcp-poc`
- [ ] Se existir `.terraform/terraform.tfstate`, confirmar que NÃO contém referências a `connect-mcp-poc`

**Como verificar:**
```powershell
# Buscar referências MCP em qualquer arquivo de estado
Get-ChildItem -Path terraform -Filter "*.tfstate" -Recurse |
    Select-String -Pattern "connect-mcp-poc" -SimpleMatch
# Resultado esperado: NENHUM match
```

### 2. Backend Remoto

- [ ] **Nenhuma configuração de backend remoto aponta para estado da POC MCP**
- [ ] Se usar backend S3, a key/path é exclusiva da POC Bedrock (ex: `connect-bedrock-poc/terraform.tfstate`)
- [ ] Se usar backend local, o estado pertence exclusivamente à POC Bedrock

**Como verificar:**
```powershell
# Inspecionar configuração de backend
Select-String -Path terraform/providers.tf, terraform/terraform.tf `
    -Pattern "connect-mcp-poc" -SimpleMatch
# Resultado esperado: NENHUM match
```

### 3. Workspace Terraform

- [ ] **O workspace ativo é dedicado à POC Bedrock**
- [ ] O workspace NÃO é compartilhado com a POC MCP
- [ ] Se usar workspace `default`, confirmar que o estado não contém recursos MCP

**Como verificar:**
```powershell
# Verificar workspace ativo
Set-Location terraform
terraform workspace show
# Resultado esperado: workspace dedicado à POC Bedrock (ex: "default" ou "bedrock-poc")
```

### 4. Prefixo de Recurso

- [ ] **`locals.prefix` em `terraform/locals.tf` é `"connect-bedrock-poc"`**
- [ ] O prefixo NÃO é `"connect-mcp-poc"`
- [ ] Todos os nomes de recursos derivados usam o prefixo correto

**Como verificar:**
```powershell
# Verificar valor do prefixo
Select-String -Path terraform/locals.tf -Pattern 'prefix\s*=' |
    Select-String -Pattern "connect-bedrock-poc"
# Resultado esperado: match encontrado com "connect-bedrock-poc"
```

> **NOTA:** Na data de criação deste checklist, `terraform/locals.tf` ainda usa o prefixo
> `connect-mcp-poc`. A alteração para `connect-bedrock-poc` é uma pendência planejada para a
> Fase 4 do plano de implementação. Até essa alteração ser feita, o plan NÃO deve ser executado
> contra a infraestrutura existente da POC MCP.

### 5. Análise do Plan Output

- [ ] **O output de `terraform plan` NÃO contém destroy ou replace de recursos `connect-mcp-poc-*`**
- [ ] Nenhuma linha do plan menciona `connect-mcp-poc` em operações de destroy
- [ ] Nenhuma linha do plan menciona `connect-mcp-poc` em operações de replace (force new)
- [ ] Nenhum `terraform import` foi executado para recursos da POC MCP

**Como verificar:**
```powershell
# Salvar plan em arquivo e inspecionar
Set-Location terraform
terraform plan -out=plan.tfplan
terraform show plan.tfplan | Select-String -Pattern "connect-mcp-poc"
# Resultado esperado: NENHUM match — se houver, ABORT imediato
```

---

## Critério de Abort

| Condição | Ação |
|----------|------|
| Qualquer `.tfstate` contém `connect-mcp-poc` | ❌ **ABORT** — Remover estado contaminado |
| Backend remoto aponta para key MCP | ❌ **ABORT** — Corrigir configuração de backend |
| `locals.prefix` é `connect-mcp-poc` (antes da Fase 4) | ⚠️ **BLOCK** — Não executar plan até Fase 4 concluída |
| Plan output menciona `connect-mcp-poc` | ❌ **ABORT** — Investigar causa raiz antes de prosseguir |
| `terraform import` de recurso MCP detectado | ❌ **ABORT** — Reverter import imediatamente |

**Regra de ouro:** Se em dúvida, NÃO execute o plan. Consulte este checklist primeiro.

---

## Script Conceitual de Validação Pré-Plan

O script abaixo será implementado em `scripts/validate_pre_plan.ps1` e DEVE ser executado
antes de qualquer `terraform plan`:

```powershell
<#
.SYNOPSIS
    Validação pré-plan para proteção contra impacto na POC MCP.

.DESCRIPTION
    Executa todas as verificações do checklist de segurança antes de permitir
    a execução de terraform plan/apply. Aborta com código de saída 1 se qualquer
    verificação falhar.

.EXAMPLE
    .\scripts\validate_pre_plan.ps1
    # Deve ser executado ANTES de qualquer terraform plan
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$FORBIDDEN_PATTERN = "connect-mcp-poc"
$EXPECTED_PREFIX = "connect-bedrock-poc"
$TerraformDir = Join-Path $PSScriptRoot ".." "terraform"
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
Write-Host "=" * 60
Write-Host " VALIDACAO PRE-PLAN — Protecao contra impacto na POC MCP"
Write-Host "=" * 60
Write-Host ""

# --- Verificação 1: Nenhum .tfstate contém referência MCP ---
Write-Host "--- Verificacao 1: Estado Terraform ---"

$stateFiles = Get-ChildItem -Path $TerraformDir -Filter "*.tfstate" -Recurse -ErrorAction SilentlyContinue
$stateContaminated = $false

foreach ($file in $stateFiles) {
    $matches = Select-String -Path $file.FullName -Pattern $FORBIDDEN_PATTERN -SimpleMatch
    if ($matches) {
        $stateContaminated = $true
        Write-Check -Name "Estado '$($file.Name)' livre de referencias MCP" -Passed $false `
            -Detail "Encontrado '$FORBIDDEN_PATTERN' em $($file.FullName)"
    }
}

if (-not $stateContaminated) {
    Write-Check -Name "Nenhum .tfstate contaminado com referencias MCP" -Passed $true
}

# --- Verificação 2: Backend não aponta para MCP ---
Write-Host ""
Write-Host "--- Verificacao 2: Backend Remoto ---"

$backendFiles = @("providers.tf", "terraform.tf") |
    ForEach-Object { Join-Path $TerraformDir $_ } |
    Where-Object { Test-Path $_ }

$backendContaminated = $false
foreach ($file in $backendFiles) {
    $matches = Select-String -Path $file -Pattern $FORBIDDEN_PATTERN -SimpleMatch
    if ($matches) {
        $backendContaminated = $true
        Write-Check -Name "Backend em '$([System.IO.Path]::GetFileName($file))' livre de referencias MCP" `
            -Passed $false -Detail "Encontrado '$FORBIDDEN_PATTERN'"
    }
}

if (-not $backendContaminated) {
    Write-Check -Name "Configuracao de backend livre de referencias MCP" -Passed $true
}

# --- Verificação 3: Prefixo em locals.tf ---
Write-Host ""
Write-Host "--- Verificacao 3: Prefixo de Recurso ---"

$localsFile = Join-Path $TerraformDir "locals.tf"
if (Test-Path $localsFile) {
    $localsContent = Get-Content $localsFile -Raw
    $prefixMatch = [regex]::Match($localsContent, 'prefix\s*=\s*"([^"]+)"')

    if ($prefixMatch.Success) {
        $currentPrefix = $prefixMatch.Groups[1].Value
        $prefixCorrect = $currentPrefix -eq $EXPECTED_PREFIX

        Write-Check -Name "locals.prefix = '$EXPECTED_PREFIX'" -Passed $prefixCorrect `
            -Detail "Valor atual: '$currentPrefix'"
    } else {
        Write-Check -Name "locals.prefix definido" -Passed $false `
            -Detail "Nao foi possivel encontrar definicao de prefix em locals.tf"
    }
} else {
    Write-Check -Name "locals.tf existe" -Passed $false `
        -Detail "Arquivo $localsFile nao encontrado"
}

# --- Verificação 4: Plan output (se disponível) ---
Write-Host ""
Write-Host "--- Verificacao 4: Workspace Terraform ---"

$workspaceResult = $null
try {
    Push-Location $TerraformDir
    $workspaceResult = terraform workspace show 2>&1
    Pop-Location
    Write-Check -Name "Workspace ativo: '$workspaceResult'" -Passed $true
} catch {
    Pop-Location
    Write-Check -Name "Workspace verificavel" -Passed $false `
        -Detail "Nao foi possivel verificar workspace: $_"
}

# --- Resultado Final ---
Write-Host ""
Write-Host "=" * 60

if ($FailCount -eq 0) {
    Write-Host " RESULTADO: TODAS AS VERIFICACOES PASSARAM" -ForegroundColor Green
    Write-Host " Seguro para executar terraform plan." -ForegroundColor Green
    Write-Host "=" * 60
    exit 0
} else {
    Write-Host " RESULTADO: $FailCount VERIFICACAO(OES) FALHARAM" -ForegroundColor Red
    Write-Host " ABORT: NAO execute terraform plan ate resolver os problemas acima." -ForegroundColor Red
    Write-Host "=" * 60
    exit 1
}
```

---

## Validação Pós-Plan

Mesmo que o script pré-plan passe, a análise do plan output é **obrigatória**:

```powershell
# Após terraform plan, inspecionar o output
$planOutput = terraform plan -no-color 2>&1 | Out-String

if ($planOutput -match "connect-mcp-poc") {
    Write-Host "ABORT: Plan contém referência a connect-mcp-poc!" -ForegroundColor Red
    Write-Host "Operações que mencionam recursos MCP:" -ForegroundColor Yellow
    $planOutput -split "`n" |
        Where-Object { $_ -match "connect-mcp-poc" } |
        ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    exit 1
}
```

---

## Quando Usar Este Checklist

Este checklist DEVE ser consultado e/ou o script executado em:

1. **Antes de qualquer `terraform plan`** — obrigatório
2. **Antes de qualquer `terraform apply`** — obrigatório
3. **Após alteração de `terraform/locals.tf`** — re-verificar prefixo
4. **Após alteração de backend configuration** — re-verificar isolamento
5. **Após merge de branches** — re-verificar estado não contaminado
6. **Em code review** — revisor deve confirmar que o checklist foi executado

---

## Referências

- Design Document §2: Princípios de isolamento
- Requisito 9.11: Terraform plan NÃO DEVE destruir ou substituir recursos com prefixo `connect-mcp-poc`
- Requisito 15.5: Pre-plan checklist
- Requisito 15.6: Critérios de abort
