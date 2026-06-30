---
inclusion: auto
---

# AWS Debugging — Regras obrigatórias

## Validação antes de declarar resolvido

1. **Smoke test real contra AWS** deve retornar exit code 0
2. Nunca confiar apenas em testes ASGI locais para Lambda
3. Verificar hash local vs `CodeSha256` remoto antes de investigar bugs
4. Verificar versão MCP no ZIP (1.10.1) vs local (1.28.0)

## Lambda Function URL + MCP

- Rota registrada pelo MCP 1.10.1: **Mount** em `/mcp` (requer `/mcp/` no scope)
- Mangum normaliza `rawPath="/mcp/"` → `scope.path="/mcp"` (remove trailing slash)
- `FunctionUrlPathWrapper` restaura o path original do `aws.event.rawPath`
- Terraform MCP_SERVER_URL deve terminar em `/mcp/`
- `redirect_slashes=False` obrigatório
- `dns_rebinding_protection=False` obrigatório para host Lambda URL
- `lifespan="on"` obrigatório (task group)
- Nova instância FastMCP/app/Mangum por invocação (session manager single-use)

## Comandos de diagnóstico

```powershell
.\scripts\smoke_test_mcp.ps1 -Profile connect-poc -Region us-east-1
.\scripts\diagnose_mcp.ps1 -Profile connect-poc -Region us-east-1
```

## Nunca fazer sem revisão

- `terraform apply` com destroy ou replace
- Reutilizar plan salvo após rebuild do ZIP
- Alterar `/mcp` ↔ `/mcp/` por tentativa (verificar Route vs Mount primeiro)
- Commit com logs de diagnóstico temporários
