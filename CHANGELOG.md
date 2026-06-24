# Changelog

## [Unreleased]

### Fase 2 — MCP local (concluída)

**Adicionado:**
- Documentos fictícios de suporte (5 documentos + 4 procedimentos) em `sample_documents/`
- MCP Server com FastMCP (`mcp` v1.28.0), modo `stateless_http=True`, `json_response=True`
- 3 tools: `search_support_documentation`, `get_support_procedure`, `health_check`
- Handler Lambda via Mangum (`mcp_server/handler.py`)
- Servidor local (`python -m mcp_server.local`) em http://localhost:8000/mcp
- Cliente MCP via Streamable HTTP (`shared/mcp_client/client.py`)
- Seletor determinístico de tools por palavras-chave (`shared/mcp_client/tool_selector.py`)
- Motor de chat testável (`local_chat/chat_engine.py`)
- Chat local interativo (`python -m local_chat --direct`)
- 86 testes unitários com cobertura de 80.41%
- Factory `create_mcp_server(environment)` para isolar config de testes

**Descobertas e limitações:**
- MCP SDK v1.28.0 exige proteção DNS rebinding: header `Host` deve estar em `allowed_hosts`, caso contrário retorna HTTP 421 Misdirected Request
- Header `Accept: application/json` obrigatório no endpoint `/mcp`; sem ele retorna 406 Not Acceptable
- FastMCP precisa de lifespan ASGI para task group; em Lambda usa-se `Mangum(app, lifespan="off")`; em testes usa-se `asgi-lifespan.LifespanManager`
- Busca por palavras-chave requer normalização Unicode (remoção de acentos) para funcionar com português

**Política de erros do MCP Client:**
- Erros de negócio (tool não encontrou documento, procedure inexistente) → `ToolResult(success=True, data={...})` com campos indicando ausência
- Erros de validação/entrada inválida (HTTP 400) → `MCPClientError` propagada
- Erros transitórios (timeout, connection refused, HTTP 5xx) → `ToolResult(success=False, error=...)` após retry
- Na futura Lambda Integrator: erros transitórios devem causar falha do registro SQS (retry automático → DLQ após 3 tentativas)

---

### Fase 1 — Arquitetura e validação (concluída)

**Adicionado:**
- Definição da arquitetura completa (ARCHITECTURE.md)
- Validação de APIs do Amazon Connect (StartContactStreaming, CreateParticipant, CreateParticipantConnection)
- Separação de fluxos Customer vs CUSTOM_BOT
- Decisão: Lambda Function URL com AWS_IAM (endpoint público, protegido por SigV4)
- Decisão: FastMCP + Mangum + stateless_http + json_response
- Decisão: seleção de tool determinística por palavras-chave (sem IA/LLM)
- Modelo DynamoDB para sessões e idempotência
- Documentação do limite de 15 segundos entre CreateParticipant e CreateParticipantConnection
- Estratégia de renovação de ConnectionToken expirado
- Estrutura do repositório
