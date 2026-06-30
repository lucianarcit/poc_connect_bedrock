# Skill: Connect Bedrock Debugger

## Contexto

Esta skill auxilia na investigacao de problemas no fluxo Amazon Connect + Bedrock Converse API.

Arquitetura: Chat Widget -> Contact Flow -> Initializer Lambda -> StartContactStreaming -> SNS -> SQS -> Integrator Lambda -> BedrockClient -> Bedrock Converse API -> Participant Service -> Usuario

## Regras obrigatorias

1. Nunca declarar problema resolvido sem smoke test real executado com sucesso
2. Nunca executar terraform apply, commit ou push sem autorizacao explicita
3. Nunca alterar o projeto MCP original
4. Nunca registrar prompts ou respostas sensiveis em logs ou documentos
5. Verificar modelo e regiao antes de atribuir erro ao codigo
6. Distinguir AccessDeniedException, model unavailable, throttling e timeout
7. Sempre buscar por correlation_id nos logs antes de concluir investigacao
8. Gerar novo Terraform plan apos cada build
9. Nao reutilizar plan apos rebuild (hashes mudam)

## Fluxo de investigacao

1. Identificar o correlation_id da mensagem com problema
2. Buscar em CloudWatch Logs do Integrator por esse correlation_id
3. Verificar sequencia esperada: parsing -> idempotencia -> sessao -> Bedrock -> SendMessage -> COMPLETED
4. Se parou em algum passo, identificar o erro naquele ponto
5. Classificar: erro transitorio (retry) ou fatal (FAILED_FINAL)

## Campos de log para diagnostico

- correlation_id: rastreamento ponta a ponta
- contact_id: identificar contato Connect
- message_id: identificar mensagem especifica
- model_id: modelo Bedrock invocado
- latency_ms: tempo de resposta
- error_code: codigo do erro AWS
- error_category: TRANSIENT ou FATAL
- final_status: COMPLETED, FAILED_FINAL, SKIPPED
- content_length: tamanho da mensagem (NAO o conteudo)
- response_length: tamanho da resposta (NAO o conteudo)

## Campos NUNCA presentes nos logs

- Conteudo da mensagem do usuario
- Conteudo da resposta do modelo
- ConnectionToken
- ParticipantToken
- Credenciais AWS
- Headers Authorization

## Erros comuns e acoes

| Erro | Tipo | Acao |
|------|------|------|
| ThrottlingException | Transitorio | Aguardar, verificar quotas |
| AccessDeniedException | Fatal | Verificar IAM, model access habilitado |
| ModelNotFoundException | Fatal | Verificar model ID e regiao |
| ValidationException | Fatal | Verificar parametros (maxTokens, temperature) |
| ModelTimeoutException | Transitorio | Modelo sobrecarregado, retry |
| BedrockTimeoutError | Transitorio | Verificar P99 latencia, ajustar timeout |
| TOKEN_EXPIRED | Transitorio | Token renewal deve ocorrer automaticamente |
| Session not found | Fatal | Verificar Initializer, DynamoDB TTL |

## Comandos uteis

```powershell
# Buscar logs por correlation_id
aws logs filter-log-events --log-group-name /aws/lambda/connect-bedrock-poc-dev-integrator --filter-pattern '{ $.correlation_id = "UUID" }'

# Verificar DLQ
aws sqs get-queue-attributes --queue-url <DLQ_URL> --attribute-names ApproximateNumberOfMessages

# Verificar identidade
aws sts get-caller-identity

# Testar modelo
aws bedrock-runtime converse --model-id <MODEL_ID> --messages '[{"role":"user","content":[{"text":"Ola"}]}]' --inference-config '{"maxTokens":10}'
```
