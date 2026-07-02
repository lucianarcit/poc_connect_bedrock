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
