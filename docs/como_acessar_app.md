# Como Acessar a App — POC Bedrock Converse

## Pré-requisitos

- Python 3.12+
- AWS CLI configurado com o profile `connect-poc`
- Terraform (apenas para infra)
- Infra AWS de pé (Lambdas, SNS, SQS, DynamoDB)

## Setup Inicial

```powershell
cd C:\proj\poc_connect_bedrock

# Ativar venv
.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements-dev.txt
```

## Credenciais AWS

Atualize as credenciais antes de usar:

```powershell
notepad $env:USERPROFILE\.aws\credentials
```

Verifique se estão válidas:

```powershell
aws sts get-caller-identity --profile connect-poc --region us-east-1
```

## Validar Infraestrutura

Antes de testar, sempre valide se a infra AWS está de pé:

```powershell
powershell -File scripts/validate_infra.ps1
```

Se reportar falhas, restaure com:

```powershell
# 1. Build dos pacotes Lambda
powershell -File scripts/build_lambdas.ps1

# 2. Terraform
$env:AWS_PROFILE = "connect-poc"
cd terraform
terraform init
terraform plan
terraform apply
```

## Página de Teste (Widget Connect + Bedrock)

Para testar o fluxo ponta a ponta:

**Opção 1 — Script PowerShell (recomendado):**

```powershell
powershell -File scripts/start_app.ps1
```

**Opção 2 — Duplo-clique:**

Execute `start_app.bat` na raiz do projeto.

**Opção 3 — Manual:**

```powershell
python scripts/serve_demo.py
# Abrir: http://localhost:8080/connect-bedrock-widget-test.html
```

### Instruções de Teste

1. Clique no ícone de chat (canto inferior direito)
2. Envie uma mensagem (ex: "Qual é a capital do Brasil?")
3. Aguarde a resposta (até 30s)

### Fluxo Completo

```
Widget → Contact Flow → Lambda Initializer → SNS → SQS
  → Lambda Integrator → Amazon Bedrock Converse (Nova Micro)
    → Participant API → Resposta no Widget
```

### Requisitos para o Widget Funcionar

- Infra AWS de pé (`validate_infra.ps1` deve passar)
- Contact Flow ativo no Amazon Connect
- Lambdas deployadas e com permissões corretas
- Modelo Bedrock habilitado na conta (amazon.nova-micro-v1:0)
- Credenciais AWS válidas

Se a infra estiver destruída, o widget abre mas não responde.

## Smoke Test do Bedrock

Para testar a conectividade com o Bedrock isoladamente:

```powershell
powershell -File scripts/smoke_test_bedrock.ps1
```

Requer credenciais AWS válidas e modelo habilitado na conta.

## Testes Unitários

```powershell
pytest                    # testes com cobertura (gate 80%)
ruff check src/ tests/    # lint
ruff format src/ tests/   # formata
```

## Informações da POC

| Item | Valor |
|------|-------|
| Modelo | amazon.nova-micro-v1:0 |
| Região | us-east-1 |
| Profile AWS | connect-poc |
| Prefixo recursos | connect-bedrock-poc-dev |
| Contact Flow | connect-bedrock-poc-dev-chat-flow |
