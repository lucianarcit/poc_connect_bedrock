# Amazon Connect + Bedrock Converse — POC

Prova de conceito que integra Amazon Connect (chat) com Amazon Bedrock Converse API, utilizando AWS Lambda como camada de processamento e Terraform como infraestrutura como código.

## Objetivo

Demonstrar o fluxo completo:

1. Usuário envia pergunta no chat do Amazon Connect
2. A mensagem trafega por SNS → SQS → Lambda Integrator
3. A Lambda consulta o Amazon Bedrock (Converse API) com o modelo Amazon Nova Micro
4. A resposta retorna ao mesmo chat via Participant API

**Modelo utilizado:** `amazon.nova-micro-v1:0`
**Região:** `us-east-1`
**Profile AWS:** `connect-poc`

## Arquitetura

```
Amazon Connect Widget
  → Contact Flow
    → Lambda Initializer (setup bot + streaming)
      → SNS → SQS
        → Lambda Integrator
          → Amazon Bedrock Converse API (Nova Micro)
            → Participant API
              → Resposta no widget
```

## Estrutura do Repositório

```
poc_connect_bedrock/
├── README.md                  # Este arquivo
├── ARCHITECTURE.md            # Decisões de arquitetura e diagramas
├── SECURITY.md                # Práticas de segurança
├── COSTS.md                   # Estimativa de custos AWS
├── CHANGELOG.md               # Histórico de alterações
├── Makefile                   # Comandos make (install, test, lint, build)
├── pyproject.toml             # Configuração do projeto Python
├── requirements-dev.txt       # Dependências para desenvolvimento
├── .env.example               # Modelo de variáveis de ambiente
├── start_app.bat              # Duplo-clique para iniciar servidor de teste
│
├── docs/                      # Documentações operacionais
│   ├── como_acessar_app.md      # Guia completo para rodar a app
│   ├── amazon-connect-setup.md  # Configuração da instância Connect
│   ├── contact-flow.md          # Detalhes do Contact Flow
│   ├── deployment.md            # Guia de deploy (Terraform + Lambdas)
│   ├── troubleshooting.md       # Problemas comuns e soluções
│   └── dlq-runbook.md           # Runbook para DLQ
│
├── demo/                      # Página de teste do widget
│   └── connect-bedrock-widget-test.html
│
├── src/                       # Código Python
│   ├── initializer/              # Lambda Initializer (setup do bot no chat)
│   ├── integrator/               # Lambda Integrator (processa mensagens + Bedrock)
│   ├── local_chat/               # Modo de teste local (terminal, usa MCP fictício)
│   ├── mcp_server/               # Servidor MCP fictício (da POC anterior, mantido como referência)
│   └── shared/                   # Código compartilhado
│       ├── bedrock_client/          # Cliente Amazon Bedrock Converse API
│       ├── mcp_client/             # Cliente MCP (da POC anterior)
│       └── crypto.py               # Criptografia KMS
│
├── terraform/                 # Infraestrutura como código
│
├── scripts/                   # Scripts de build, validação e execução
│   ├── build_lambdas.ps1        # Build dos pacotes Lambda
│   ├── validate_infra.ps1       # Validação da infra AWS
│   ├── start_app.ps1            # Inicia servidor + abre navegador
│   ├── smoke_test_bedrock.ps1   # Teste de conectividade com Bedrock
│   └── serve_demo.py            # Servidor HTTP para o widget
│
├── packages/                  # ZIPs das Lambdas (gerados pelo build)
│
└── tests/                     # Testes unitários e de integração (pytest)
```

## Pré-requisitos

- Python 3.12+
- Terraform >= 1.6
- AWS CLI configurado (profile `connect-poc`)
- Conta AWS com Amazon Connect habilitado e modelo Bedrock ativado

## Início Rápido

```powershell
# 1. Ativar venv
.venv\Scripts\Activate.ps1

# 2. Instalar dependências
pip install -r requirements-dev.txt

# 3. Validar infra AWS
powershell -File scripts/validate_infra.ps1

# 4. Iniciar app de teste
powershell -File scripts/start_app.ps1
# Ou: duplo-clique em start_app.bat
```

## Teste Ponta a Ponta (Widget)

1. Execute `start_app.bat` ou `powershell -File scripts/start_app.ps1`
2. O navegador abre em `http://localhost:8080/connect-bedrock-widget-test.html`
3. Clique no ícone de chat (canto inferior direito)
4. Envie uma pergunta (ex: "Qual é a capital do Brasil?")
5. Aguarde a resposta do Bedrock (até 30s)

**Requisitos:** Infra AWS de pé (execute `validate_infra.ps1` antes).

## Testes Unitários

```powershell
pytest                    # roda testes com cobertura (gate 80%)
ruff check src/ tests/    # lint
ruff format src/ tests/   # formata
```

**Cobertura mínima exigida:** 80%

## Deploy da Infraestrutura

```powershell
# Build dos pacotes Lambda
powershell -File scripts/build_lambdas.ps1

# Terraform
$env:AWS_PROFILE = "connect-poc"
cd terraform
terraform init
terraform plan
terraform apply  # requer autorização explícita
```

## Dependências Principais

| Pacote | Versão | Papel |
|--------|--------|-------|
| `boto3` | >=1.34.0 | SDK AWS (Bedrock, Connect, DynamoDB, KMS) |
| `pydantic` | >=2.0.0 | Validação de modelos |
| `pytest` | >=8.0.0 | Testes |
| `moto` | >=5.0.0 | Mock AWS para testes |

## Documentação

- **[Como Acessar a App](docs/como_acessar_app.md)** — Guia completo para rodar localmente
- [Troubleshooting](docs/troubleshooting.md) — Problemas comuns e soluções
- [Arquitetura](ARCHITECTURE.md) — Decisões e diagramas
- [Deploy](docs/deployment.md) — Guia de deploy
- [DLQ Runbook](docs/dlq-runbook.md) — Inspeção e redrive

## Status

| Fase | Descrição | Status |
|------|-----------|--------|
| 1 | Arquitetura e validação | ✅ Concluída |
| 2 | Lambdas (Initializer + Integrator) | ✅ Concluída |
| 3 | Bedrock Converse API | ✅ Concluída |
| 4 | Terraform | ✅ Concluída |
| 5 | Amazon Connect (Contact Flow + Widget) | ✅ Concluída |
| 6 | Validação ponta a ponta | ✅ Concluída |
