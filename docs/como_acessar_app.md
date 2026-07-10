Pré-requisitos
Python 3.12+
AWS CLI configurado com o profile connect-poc (para smoke tests e Lambda)
Terraform (apenas para infra, não para rodar local)
Setup
cd C:\proj\poc_connect_bedrock

# Criar/ativar venv (já existe .venv)
.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements-dev.txt
Copiar variáveis de ambiente
copy .env.example .env
# Preencher os valores no .env (instance ID, ARNs, etc.)
Rodar localmente
Há dois modos de chat local disponíveis:

Opção 1: Modo direto (sem servidor HTTP)
O mais simples — usa os documentos de sample_documents/ diretamente:

cd src
python -m local_chat --direct
Opção 2: Com servidor MCP local
Terminal 1 — iniciar o servidor:

cd src
python -m mcp_server.local
# Sobe em http://localhost:8000/mcp
Terminal 2 — chat:

cd src
python -m local_chat --server-url http://localhost:8000/mcp
Testes
pytest                    # roda testes com cobertura (gate 80%)
ruff check src/ tests/    # lint
ruff format src/ tests/   # formata
Página de Teste (Widget Connect)
Para testar o fluxo ponta a ponta com o widget do Amazon Connect:

Terminal 1 — iniciar servidor local:

python scripts/serve_demo.py

Abrir no navegador:

http://localhost:8080/connect-bedrock-widget-test.html

Instruções:
1. Clique no ícone de chat (canto inferior direito)
2. Envie uma mensagem de teste (ex: "Qual é a capital do Brasil?")
3. Aguarde a resposta (até 30s)

Requisitos para o widget funcionar:
- Infra AWS precisa estar de pé (terraform apply executado)
- Contact Flow ativo
- Lambdas deployadas
- SNS/SQS configurados
- Credenciais AWS válidas na conta

Se a infra estiver destruída, o widget abre mas não responde.

Observações
O local_chat testa o fluxo MCP (POC-01), não o fluxo Bedrock Converse direto (POC-02). O fluxo Bedrock direto exige a infra AWS real (Contact Flow → Lambda → Bedrock).
Para testar o Bedrock Converse isoladamente, use: powershell -File scripts/smoke_test_bedrock.ps1 (requer credenciais AWS válidas e modelo habilitado na conta).

Para usá-la:

Abra o arquivo diretamente no navegador — basta dar duplo-clique ou:

python -m local_chat --server-url http://localhost:8000/mcpcd

start demo\connect-bedrock-widget-test.html
Clique no ícone de chat (canto inferior direito da página)

Envie uma mensagem de teste como: "Qual é a capital do Brasil? Responda em uma frase."

Aguarde a resposta (até 30s) — ela percorre o fluxo completo: Widget → Contact Flow → Lambda Initializer → SNS → SQS → Lambda Integrator → Bedrock Nova Micro → Participant API → Widget

Requisitos para funcionar:

A infra AWS precisa estar de pé (Lambdas deployadas, Contact Flow ativo, SNS/SQS configurados)
O widget carrega o script do seu Connect instance (mcp-poc-dev.my.connect.aws)
Credenciais e permissões IAM corretas na conta
Se a infra estiver destruída ou parada, o widget vai abrir mas não vai receber resposta. Precisa do terraform apply ter sido executado antes.