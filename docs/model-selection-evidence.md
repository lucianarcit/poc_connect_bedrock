# Evidencia de Selecao do Modelo — POC-01 Bedrock Converse

## Decisao Final

| Item | Valor |
|------|-------|
| Model ID | `amazon.nova-micro-v1:0` |
| ARN | `arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0` |
| Regiao | `us-east-1` |
| Tipo | Foundation model (invocacao direta, sem inference profile) |
| API | Amazon Bedrock Converse API |
| Data da validacao | 2026-07-02 |

## Justificativa

O Amazon Nova Micro foi escolhido para a POC pelos seguintes motivos:

1. **Disponibilidade confirmada** — modelo ativo em `us-east-1` sem necessidade de habilitacao adicional ou aceite de EULA
2. **Suporte a Converse API** — validado com chamada real usando `bedrock-runtime converse`
3. **Baixo custo** — modelo mais economico da familia Amazon Nova, adequado para POC
4. **Baixa latencia** — resposta em 238ms na medicao pontual (ver metricas abaixo)
5. **Sem inference profile** — invocacao direta como foundation model, ARN simples e validado
6. **Portugues funcional** — resposta coerente em pt-BR no smoke test

## Metricas do Smoke Test Real

| Metrica | Valor |
|---------|-------|
| Input tokens | 8 |
| Output tokens | 5 |
| Total tokens | 13 |
| Latencia | 238 ms |
| Stop reason | `end_turn` |
| Resultado | `BEDROCK_OK` |

### Condicoes do teste

- Data: 2026-07-02
- Regiao: us-east-1
- Horario: durante expediente
- Amostras: 1 (medicao pontual)
- Pergunta: curta em portugues (< 50 caracteres)

> **IMPORTANTE:** 238 ms e uma medicao pontual, NAO um SLA ou P50 garantido.
> A latencia real deve ser monitorada apos o deploy com multiplas amostras
> sob condicoes reais de carga.

## Foundation Model vs Inference Profile

- O model ID `amazon.nova-micro-v1:0` NAO possui prefixo regional (`us.`, `eu.`, `ap.`)
- Portanto, e invocado como **foundation model direto**
- NAO foi necessario usar inference profile
- O ARN foi obtido com `aws bedrock get-foundation-model --model-identifier amazon.nova-micro-v1:0`
- O ARN validado usa formato: `arn:aws:bedrock:<region>::foundation-model/<model-id>`

## IAM

- Resource no IAM policy: `arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0`
- Wildcard NAO necessario — ARN especifico funciona
- Testado via smoke test com a role configurada

## Troca futura de modelo

O modelo pode ser trocado a qualquer momento alterando:

1. `bedrock_model_id` no `terraform.tfvars`
2. `bedrock_model_arn` no `terraform.tfvars`
3. Executar novo `terraform plan` + `apply`

Nenhuma alteracao de codigo e necessaria. O BedrockClient le o model ID da variavel de ambiente.

## Monitoramento pos-deploy

Apos o deploy, monitorar:

- Latencia P50, P90, P99 via CloudWatch Logs (`latency_ms`)
- Custo via AWS Cost Explorer (filtro por Bedrock)
- Throttling via alarme `integrator-throttles`
- Qualidade das respostas em portugues (validacao manual)

## Candidatos avaliados

| Modelo | Status | Notas |
|--------|--------|-------|
| Amazon Nova Micro | **SELECIONADO** | Menor custo, latencia baixa, pt-BR funcional |
| Amazon Nova Lite | Candidato backup | Maior capacidade; usar se Micro nao atender qualidade |
| Claude 3 Haiku | Nao testado | Requer aceite EULA; avaliar se necessario |

## Teste Ponta a Ponta — Resultado Final

| Item | Valor |
|------|-------|
| Data do teste | 2026-07-02 |
| Contact Flow | connect-bedrock-poc-dev-chat-flow |
| Widget | connect-bedrock-poc-dev-chat-widget |
| Contact ID | 81ebc9bb-**** (parcialmente mascarado) |
| Correlation ID | 20687a22-8c9f-42bf-b38c-83927d97408d |
| Pergunta | "Qual a capital de Minas Gerais" |
| Resposta | "Belo Horizonte" (recebida no widget) |
| Content length | 31 chars |
| Response length | 260 chars |
| Latencia Bedrock | 509.2 ms |
| Latencia total (Initializer + Integrator) | ~5s (inclui cold start) |
| SQS apos teste | 0 mensagens |
| DLQ apos teste | 0 mensagens |
| Erros | Zero (nenhum ERROR, timeout, AccessDenied) |
| MESSAGEMETADATA | Corretamente ignorado |
| Roles ignoradas | SYSTEM, CUSTOM_BOT filtrados |
| Status final | COMPLETED |

### Fluxo confirmado ponta a ponta

```
Widget → Contact Flow → Initializer (SUCCESS, 2897ms)
→ StartContactStreaming → SNS → SQS
→ Integrator → BedrockClient → Converse API (509ms)
→ Participant Service → resposta no Widget
```

## Licao Aprendida — Estrutura dos ZIPs

### Problema encontrado

Na primeira tentativa de chat, a Lambda Initializer falhou com:
```
Runtime.ImportModuleError: Unable to import module 'initializer.handler': No module named 'initializer'
```

### Causa raiz

Build manual com `Compress-Archive -Path "src/initializer/*"` coloca arquivos na raiz do ZIP. O handler `initializer.handler.handler` exige que os arquivos estejam dentro do diretorio `initializer/`.

### Correcao

Usar exclusivamente `scripts/build_lambdas.ps1` que preserva a estrutura de diretorios Python:
- `initializer/handler.py` (nao `handler.py` na raiz)
- `integrator/handler.py` (nao `handler.py` na raiz)
- `shared/bedrock_client/...`

### Regra permanente

- NUNCA usar `Compress-Archive` diretamente sobre `src/<modulo>/*`
- SEMPRE usar `scripts/build_lambdas.ps1`
- SEMPRE validar imports apos build: `import initializer.handler` e `import integrator.handler`
