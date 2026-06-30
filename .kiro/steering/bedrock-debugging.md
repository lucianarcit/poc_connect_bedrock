# Steering: Bedrock Debugging Workflow

## Quando usar

Quando investigar problemas no fluxo Connect -> Bedrock da POC-01.

## Workflow passo a passo

### 1. Identificar o problema

- Usuario reporta: sem resposta, resposta errada, mensagem de erro
- Alarme disparado: FailedFinal, DLQ, Errors, Throttles
- Log suspeito encontrado

### 2. Obter correlation_id

- Se o usuario tem o ID: usar diretamente
- Se alarme: buscar nos logs recentes do Integrator
- Comando: `aws logs tail /aws/lambda/connect-bedrock-poc-dev-integrator --since 5m`

### 3. Rastrear ciclo completo

Buscar todos os logs com o correlation_id:

```powershell
aws logs filter-log-events \
  --log-group-name /aws/lambda/connect-bedrock-poc-dev-integrator \
  --filter-pattern "{ $.correlation_id = \"<UUID>\" }" \
  --region us-east-1
```

### 4. Verificar sequencia esperada

| Passo | Log esperado | Se ausente |
|-------|-------------|------------|
| 1. Parsing | "SNS envelope parsed" | Erro de JSON no body |
| 2. Classificacao | "Processing message" | Evento filtrado (skip) |
| 3. Idempotencia | "Lease acquired" | Duplicata ou DynamoDB erro |
| 4. Bedrock | "Calling Bedrock Converse API" | Sessao nao encontrada |
| 5. Resposta | "Sending response to chat" | Erro do Bedrock |
| 6. Conclusao | "Message processed successfully" | Erro no SendMessage |

### 5. Classificar o erro

#### Transitorio (retry automatico)

- ThrottlingException
- ServiceUnavailableException
- ModelTimeoutException
- ReadTimeoutError
- DynamoDBTransientError

Acao: verificar se mensagem foi eventualmente processada apos retry.

#### Fatal (FAILED_FINAL)

- AccessDeniedException -> verificar IAM e model access
- ValidationException -> verificar BEDROCK_MODEL_ID, maxTokens, temperature
- ModelNotFoundException -> verificar modelo e regiao
- Session not found -> verificar Initializer

### 6. Verificar antes de atribuir erro ao codigo

- [ ] Modelo habilitado na conta? (Model access no console)
- [ ] Regiao correta? (us-east-1)
- [ ] IAM policy com bedrock:InvokeModel?
- [ ] ARN correto na policy?
- [ ] BEDROCK_MODEL_ID valido?
- [ ] Credenciais da Lambda validas?
- [ ] Timeout adequado? (P99 < BEDROCK_TIMEOUT_SECONDS)

### 7. Acoes corretivas comuns

| Problema | Acao |
|----------|------|
| AccessDenied | Verificar/corrigir IAM policy, aguardar propagacao (30-60s) |
| Model not found | Corrigir BEDROCK_MODEL_ID, verificar regiao |
| Throttling persistente | Verificar Service Quotas, considerar provisioned throughput |
| Timeout consistente | Aumentar BEDROCK_TIMEOUT_SECONDS ou trocar modelo |
| DLQ crescendo | Verificar causa raiz dos erros transitorios |

### 8. Validar correcao

1. Aplicar correcao
2. Executar smoke test: `powershell -File scripts/smoke_test_bedrock.ps1`
3. Verificar exit code 0
4. Enviar mensagem real no chat
5. Buscar correlation_id nos logs
6. Confirmar COMPLETED

## O que NAO fazer durante debugging

- Nao alterar infraestrutura MCP
- Nao executar terraform apply sem autorizacao
- Nao registrar conteudo de mensagens nos logs ou documentos
- Nao assumir modelo disponivel sem verificar
- Nao declarar resolvido sem smoke test real
- Nao reutilizar terraform plan apos rebuild
