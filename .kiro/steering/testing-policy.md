---
inclusion: auto
---

# Testing Policy

## Hierarquia de confiança

1. **Smoke test real AWS** (maior confiança)
2. Handler integration test (evento Function URL v2 → handler exportado)
3. ASGI test com LifespanManager (protocolo MCP completo)
4. Unit test com mocks (menor confiança para bugs de integração)

## Regras

- Não declarar bug resolvido apenas com unit test passando
- Sempre verificar se versão local do MCP SDK = versão no ZIP
- Testes de warm start (3 invocações) são obrigatórios para handler
- Verificar Route vs Mount antes de alterar paths
- Após rebuild, executar `pytest` E smoke test

## Antes de deploy

```powershell
python -m pytest tests/ -q                              # Todos os testes
.\scripts\build_lambdas.ps1 -Function <alterada>        # Rebuild seletivo
.\scripts\smoke_test_mcp.ps1 -Profile connect-poc       # Smoke test real (após apply)
```
