# Amazon Connect + MCP — POC

Prova de conceito que integra Amazon Connect (chat) com um servidor MCP (Model Context Protocol) fictício, utilizando AWS Lambda como camada de processamento e Terraform como infraestrutura como código.

## Objetivo

Demonstrar o fluxo completo:

1. Usuário envia pergunta no chat do Amazon Connect
2. A mensagem trafega por SNS → SQS → Lambda
3. A Lambda consulta um servidor MCP fictício
4. A resposta retorna ao mesmo chat

**Sem uso de:** Amazon Q, Amazon Lex, Bedrock ou qualquer LLM.
**Seleção de tool:** determinística por palavras-chave (sem IA).

## Estrutura do Repositório

```
amazon-connect-mcp-poc/
├── README.md                  # Este arquivo — visão geral do projeto
├── ARCHITECTURE.md            # Decisões de arquitetura, diagramas, trade-offs
├── SECURITY.md                # Práticas de segurança e riscos da POC
├── COSTS.md                   # Estimativa de custos AWS para baixo volume
├── CHANGELOG.md               # Histórico de alterações por fase
├── Makefile                   # Comandos make (install, test, lint, build, terraform)
├── pyproject.toml             # Configuração do projeto Python (deps, pytest, ruff)
├── requirements-dev.txt       # Dependências para desenvolvimento local
├── .env.example               # Modelo de variáveis de ambiente
├── .gitignore                 # Arquivos ignorados pelo Git
│
├── docs/                      # Documentações operacionais
│   ├── amazon-connect-setup.md   # Configuração da instância Connect
│   ├── contact-flow.md           # Detalhes do Contact Flow
│   ├── deployment.md             # Guia de deploy (Terraform + Lambdas)
│   ├── demo-script.md            # Roteiro de demonstração (5-10 min)
│   ├── troubleshooting.md        # Problemas comuns e soluções
│   ├── dlq-runbook.md            # Runbook para DLQ (inspeção, redrive)
│   └── diagrams/                 # Diagramas exportados (PNG, SVG)
│
├── sample_documents/          # Documentos fictícios de suporte (JSON)
│
├── src/                       # Código Python da aplicação
│   ├── initializer/              # Lambda Initializer (setup do bot no chat)
│   ├── integrator/               # Lambda Integrator (processa mensagens)
│   ├── mcp_server/               # Lambda MCP Server (tools fictícias)
│   ├── local_chat/               # Modo de teste local (terminal)
│   └── shared/                   # Código compartilhado (client MCP, crypto, modelos)
│
├── terraform/                 # Infraestrutura como código (Terraform)
│
├── scripts/                   # Scripts de build, deploy, validação e limpeza
│
└── tests/                     # Testes unitários e de integração (pytest)
```

## Pré-requisitos

- Python 3.12+
- Terraform >= 1.6
- AWS CLI configurado
- Conta AWS com Amazon Connect habilitado

## Execução Local

O chat local permite testar o fluxo MCP completo sem infraestrutura AWS.

### Modo direto (sem servidor HTTP)

```bash
cd src
python -m local_chat --direct
```

Chama as tools MCP diretamente em memória. Não requer servidor rodando.

### Modo com servidor MCP local

Terminal 1 — iniciar o servidor:
```bash
cd src
python -m mcp_server.local
```

Terminal 2 — iniciar o chat:
```bash
cd src
python -m local_chat --server-url http://localhost:8000/mcp
```

### Exemplo de interação

```
Você: como redefinir minha senha
Bot: Redefinição de senha (DOC-001)
     1. Acesse a tela de login do sistema.
     2. Clique em 'Esqueci minha senha'.
     ...

Você: qual o status
Bot: Status: healthy
     Documentos carregados: 5

Você: falar com atendente
Bot: Entendido! Vou transferir você para um atendente humano.

Você: sair
Bot: Até logo!
```

## Testes

```bash
# Instalar dependências
python -m pip install -r requirements-dev.txt

# Executar testes com cobertura
python -m pytest

# Executar testes verbose
python -m pytest -v

# Somente um módulo
python -m pytest tests/unit/test_mcp_tools.py -v
```

**Cobertura mínima exigida:** 80% (configurado em `pyproject.toml`).

**Cobertura atual:** 80.41% (86 testes).

## Dependências Principais

| Pacote | Versão | Papel |
|--------|--------|-------|
| `mcp` | 1.28.0 | SDK oficial MCP (FastMCP, Streamable HTTP) |
| `mangum` | >=0.17.0 | Adaptador ASGI → Lambda handler |
| `httpx` | >=0.27.0 | HTTP client para chamadas MCP |
| `boto3` | >=1.34.0 | SDK AWS (usado nas Lambdas) |
| `pydantic` | >=2.0.0 | Validação de modelos |

## Limitações Conhecidas (MCP SDK v1.28.0)

1. **Proteção DNS rebinding** — O SDK rejeita requests cujo header `Host` não seja localhost (retorna HTTP 421). Em testes, é necessário configurar `TransportSecuritySettings` com `allowed_hosts` explícitos. Em produção (Lambda Function URL), o host real é aceito.

2. **Header Accept obrigatório** — O endpoint `/mcp` exige `Accept: application/json`. Requests sem esse header recebem HTTP 406 Not Acceptable.

3. **Modo stateless** — Com `stateless_http=True`, não há sessão entre requests. Cada chamada JSON-RPC é independente.

4. **json_response=True** — Desabilita SSE (Server-Sent Events). Respostas são JSON puro, compatível com Lambda Function URL + Mangum.

5. **Lifespan ASGI** — O FastMCP usa lifespan events para inicializar o task group. No Lambda (Mangum), configuramos `lifespan="off"`. Em testes, usamos `asgi-lifespan.LifespanManager`.

## Status

| Fase | Descrição | Status |
|------|-----------|--------|
| 1 | Arquitetura e validação | ✅ Concluída |
| 2 | MCP local | ✅ Concluída |
| 3 | Lambdas | 🔲 Pendente |
| 4 | Terraform | 🔲 Pendente |
| 5 | Amazon Connect | 🔲 Pendente |
| 6 | Documentação | 🔲 Pendente |

## Documentação

- [Arquitetura](ARCHITECTURE.md)
- [Segurança](SECURITY.md)
- [Custos](COSTS.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Deploy](docs/deployment.md)
- [DLQ Runbook](docs/dlq-runbook.md)
