# Guia Operacional — Configuração Manual do Amazon Bedrock

## Objetivo

Este guia descreve todos os passos manuais necessários para configurar o Amazon Bedrock para a POC-01 (Connect + Bedrock Converse API). Cobre desde a verificação de acesso até a validação completa do modelo escolhido.

**Nenhum passo deste guia altera a POC MCP original.**

---

## 1. Pré-requisitos

| Item | Detalhe |
|------|---------|
| Região AWS | `us-east-1` (obrigatória para esta POC) |
| Conta AWS | Conta correta onde a POC será provisionada |
| Perfil AWS CLI | Configurado com `aws configure` ou variáveis de ambiente |
| Permissões mínimas (pessoa operadora) | `bedrock:ListFoundationModels`, `bedrock:GetFoundationModel`, `bedrock:InvokeModel`, `bedrock:ListInferenceProfiles` |
| Permissões mínimas (Lambda Integrator) | Apenas `bedrock:InvokeModel` com Resource específico |

### Diferença importante

- **Pessoa operadora (console/CLI):** precisa de permissões para listar, testar e validar modelos
- **Lambda Integrator (IAM role):** precisa apenas de `bedrock:InvokeModel` para o modelo específico

A role da Lambda NÃO deve ter `bedrock:ListFoundationModels` ou outras permissões de discovery.

---

## 2. Verificar acesso ao Amazon Bedrock

### Via Console

1. Acessar o AWS Management Console
2. Confirmar que a região selecionada é **US East (N. Virginia) / us-east-1**
3. Buscar por "Bedrock" na barra de busca
4. Abrir o serviço **Amazon Bedrock**
5. Se aparecer uma página de boas-vindas ou overview, o serviço está disponível na conta

### Verificar habilitação de modelos

1. No painel do Amazon Bedrock, procurar por uma área chamada **"Model access"**, **"Acesso a modelos"** ou equivalente (o nome pode variar conforme a versão atual do console)
2. Verificar o status dos modelos de interesse:
   - **Amazon Nova** (Lite, Micro) — geralmente disponível sem aceite adicional
   - **Anthropic Claude** — pode exigir aceite de termos de uso (EULA)
3. Se um modelo mostrar status "Not available" ou "Request access", seguir o processo de habilitação no console

> ⚠️ **Atenção:** A habilitação de modelos pode levar alguns minutos. Alguns modelos (Anthropic, Meta) exigem aceite explícito de termos.

### Via AWS CLI

```powershell
# Verificar identidade e região
aws sts get-caller-identity --region us-east-1

# Verificar se o Bedrock está acessível
aws bedrock list-foundation-models --region us-east-1 --query "modelSummaries[0].modelId" --output text
```

Se o comando retornar um model ID, o acesso está funcional.

---

## 3. Descobrir modelos disponíveis

### Via AWS CLI

```powershell
# Listar todos os modelos disponíveis
aws bedrock list-foundation-models --region us-east-1 --output json

# Filtrar apenas modelos com acesso on-demand (sem provisioned throughput)
aws bedrock list-foundation-models --region us-east-1 \
  --query "modelSummaries[?contains(inferenceTypesSupported, 'ON_DEMAND')].[modelId,modelName,providerName]" \
  --output table
```

### Campos importantes da resposta

| Campo | Significado |
|-------|-------------|
| `modelId` | Identificador usado na Converse API (ex: `amazon.nova-lite-v1:0`) |
| `modelName` | Nome amigável do modelo |
| `providerName` | Fornecedor (Amazon, Anthropic, Meta, etc.) |
| `inferenceTypesSupported` | Modos: `ON_DEMAND`, `PROVISIONED` |
| `modelLifecycle.status` | `ACTIVE`, `LEGACY` |
| `responseStreamingSupported` | Se suporta streaming |

### Candidatos recomendados para a POC

| Modelo | Prioridade | Motivo |
|--------|-----------|--------|
| Amazon Nova Micro | **SELECIONADO** | Menor custo, validado com 238ms latencia, pt-BR funcional |
| Amazon Nova Lite | Backup | Maior capacidade; usar se Micro nao atender qualidade |
| Claude 3 Haiku | 3 | Boa qualidade, requer aceite de EULA |

> **Resultado da Fase 1:** O modelo `amazon.nova-micro-v1:0` foi validado em us-east-1 via smoke test real em 2026-07-02. ARN: `arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0`. Sem inference profile. Detalhes em `docs/model-selection-evidence.md`.

### Confirmar suporte à Converse API

A Converse API suporta a maioria dos modelos ativos no Bedrock. Para confirmar:

```powershell
# Tentar uma chamada converse com o modelo — se funcionar, é suportado
aws bedrock-runtime converse \
  --region us-east-1 \
  --model-id "amazon.nova-lite-v1:0" \
  --messages '[{"role":"user","content":[{"text":"Olá"}]}]' \
  --inference-config '{"maxTokens":10}' \
  --query "output.message.content[0].text" \
  --output text
```

---

## 4. Validar um modelo

### Via Playground do Bedrock (Console)

1. No console do Amazon Bedrock, procurar por **"Playground"**, **"Chat"** ou **"Text"** (o nome pode variar)
2. Selecionar o modelo candidato
3. Configurar:
   - **System prompt:** Copiar o prompt padrão da POC:
     ```
     Você é um agente virtual de suporte. Responda sempre em português brasileiro.
     Seja claro e objetivo nas respostas. Atue como agente virtual de suporte.
     Não invente informações que não estejam disponíveis.
     Informe ao usuário quando não tiver dados suficientes para responder.
     ```
   - **Temperature:** 0.7
   - **Max tokens:** 1024
4. Enviar pergunta de teste em português: "Como faço para resetar minha senha?"
5. Verificar:
   - Resposta em português brasileiro
   - Clareza e objetividade
   - Tempo de resposta (observar latência no console)
6. Enviar mais 2-3 perguntas variadas

### Valores a registrar

| Item | Valor |
|------|-------|
| Model ID exato | Ex: `amazon.nova-lite-v1:0` |
| Região | `us-east-1` |
| Data da validação | YYYY-MM-DD |
| Qualidade do português | Boa / Aceitável / Insuficiente |
| Latência observada | Aproximada em segundos |

---

## 5. Foundation model versus inference profile

### Conceito

| Tipo | Descrição | Prefixo do ID |
|------|-----------|---------------|
| Foundation model | Modelo invocado diretamente na região | Sem prefixo regional (ex: `amazon.nova-lite-v1:0`) |
| Inference profile | Perfil de inferência cross-region gerenciado pela AWS | Com prefixo regional (ex: `us.amazon.nova-lite-v1:0`) |

### Como identificar

- Se o model ID começa com `us.`, `eu.` ou `ap.` → é um inference profile cross-region
- Se não tem prefixo regional → é invocação direta ao foundation model

### Listar inference profiles

```powershell
aws bedrock list-inference-profiles --region us-east-1 --output json
```

### Impacto no IAM

| Tipo | Formato do ARN (Resource) |
|------|---------------------------|
| Foundation model | `arn:aws:bedrock:us-east-1::foundation-model/<model-id>` |
| Inference profile | `arn:aws:bedrock:us-east-1:<account-id>:inference-profile/<profile-id>` |

> ⚠️ **Importante:** O ARN exato DEVE ser validado na conta real antes de configurar a IAM policy. Não assumir um formato sem testar.

### Verificar o ARN correto

```powershell
# Para foundation model
aws bedrock get-foundation-model \
  --model-identifier "amazon.nova-lite-v1:0" \
  --region us-east-1 \
  --query "modelDetails.modelArn" \
  --output text
```

---

## 6. Teste via AWS CLI ou Python

### Teste com AWS CLI

```powershell
aws bedrock-runtime converse \
  --region us-east-1 \
  --model-id "<MODEL_ID>" \
  --system '[{"text":"Responda em português brasileiro. Seja claro e objetivo."}]' \
  --messages '[{"role":"user","content":[{"text":"Qual é a capital do Brasil?"}]}]' \
  --inference-config '{"maxTokens":256,"temperature":0.7}' \
  --query "output.message.content[0].text" \
  --output text
```

### Teste com Python (mesma classe da Lambda)

```python
import os
os.environ["BEDROCK_MODEL_ID"] = "<MODEL_ID>"
os.environ["AWS_REGION"] = "us-east-1"

from shared.bedrock_client import BedrockClient

client = BedrockClient()
response = client.converse(
    user_message="Qual é a capital do Brasil?",
    correlation_id="teste-manual-001",
)
print(f"Resposta: {response}")
```

### Erros comuns nesta etapa

| Erro | Causa provável |
|------|----------------|
| `AccessDeniedException` | IAM sem permissão `bedrock:InvokeModel` para o modelo |
| `ValidationException` | Model ID inválido ou parâmetros incompatíveis |
| `ModelNotFoundException` | Modelo não existe na região ou não está habilitado |
| `ThrottlingException` | Rate limit excedido (aguardar e retentar) |

> ⚠️ **Segurança:** Não registrar o conteúdo das mensagens ou respostas em logs compartilhados. Usar apenas para validação local.

---

## 7. IAM

### Permissão necessária para a Lambda Integrator

A role IAM da Lambda Integrator precisa de:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInvokeModel",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "<ARN validado do modelo>"
    }
  ]
}
```

### Diferença entre permissões

| Quem | Permissões necessárias | Motivo |
|------|------------------------|--------|
| Pessoa operadora | `bedrock:*` (ou subset amplo) | Listar, testar, validar modelos |
| Lambda Integrator | Apenas `bedrock:InvokeModel` | Executar inferência no modelo específico |

### ARN específico versus wildcard

| Cenário | Resource | Quando usar |
|---------|----------|-------------|
| ARN específico funciona | `arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0` | Sempre que possível (menor privilégio) |
| Wildcard necessário | `arn:aws:bedrock:us-east-1::foundation-model/*` | Apenas se resource-level permissions não forem suportadas |

> Se wildcard for necessário, documentar como limitação conhecida em `docs/known-limitations.md`.

### Validar a policy

Após aplicar a policy na role da Lambda:
1. Executar o smoke test (`scripts/smoke_test_bedrock.ps1`)
2. Se `AccessDeniedException`, revisar: ARN, Account ID, região, propagação (~30s)

---

## 8. Variáveis que devem ser definidas

| Variável | Tipo | Obrigatória | Padrão | Onde definir |
|----------|------|-------------|--------|--------------|
| `BEDROCK_MODEL_ID` | string | **Sim** | — | Terraform `var.bedrock_model_id` → Lambda env |
| `BEDROCK_MAX_TOKENS` | int | Não | 1024 | Terraform → Lambda env |
| `BEDROCK_TEMPERATURE` | float | Não | 0.7 | Terraform → Lambda env |
| `BEDROCK_SYSTEM_PROMPT` | string | Não | Prompt padrão pt-BR | Terraform → Lambda env |
| `BEDROCK_TIMEOUT_SECONDS` | int | Não | 20 | Terraform → Lambda env |
| `AWS_REGION` | string | Não | us-east-1 | Implícito no Lambda runtime |

### Valor obrigatório sem default

`BEDROCK_MODEL_ID` **não tem valor padrão**. O Terraform exige que o operador forneça explicitamente após validação via smoke test. Se a variável estiver ausente, a Lambda falha no cold start com `BedrockConfigurationError`.

---

## 9. Checklist antes do smoke test

Antes de executar `scripts/smoke_test_bedrock.ps1`, confirmar:

- [ ] Modelo acessível na conta (get-foundation-model sem erro)
- [ ] Converse API funcionando para o modelo (teste CLI retorna texto)
- [ ] Model ID exato registrado em `docs/model-selection-evidence.md`
- [ ] ARN validado para IAM policy
- [ ] IAM policy da Lambda revisada com ARN correto
- [ ] Região confirmada: `us-east-1`
- [ ] Credenciais AWS válidas (`aws sts get-caller-identity`)
- [ ] System prompt validado no playground (resposta em pt-BR)
- [ ] `BEDROCK_MODEL_ID` configurada no ambiente do smoke test
- [ ] Timeout adequado (P99 da latência < 20s)

---

## 10. Troubleshooting

### AccessDeniedException

| Sintoma | Causa | Ação |
|---------|-------|------|
| "User is not authorized to perform: bedrock:InvokeModel" | IAM policy ausente ou ARN incorreto | Verificar policy, ARN e região |
| Ocorre logo após apply | Eventual consistency do IAM | Aguardar 30-60s e retentar |
| Funciona no CLI mas não na Lambda | Role da Lambda sem a permission | Verificar role ARN no Terraform |

### ModelNotFoundException

| Sintoma | Causa | Ação |
|---------|-------|------|
| "Could not resolve model identifier" | Model ID inválido ou typo | Verificar com `list-foundation-models` |
| Modelo existe mas não está habilitado | Model access não concedido | Habilitar no console |
| Modelo existe em outra região | Região incorreta | Confirmar `us-east-1` |

### ValidationException

| Sintoma | Causa | Ação |
|---------|-------|------|
| "Invalid model identifier" | Model ID com formato incorreto | Usar ID exato do `list-foundation-models` |
| "maxTokens must be..." | Valor fora do range do modelo | Ajustar `BEDROCK_MAX_TOKENS` |
| "temperature must be..." | Valor fora de [0.0, 1.0] | Ajustar `BEDROCK_TEMPERATURE` |

### ThrottlingException

| Sintoma | Causa | Ação |
|---------|-------|------|
| "Rate exceeded" | Muitas chamadas simultâneas | Aguardar e retentar (exponential backoff) |
| Persistente | Cota de tokens/min excedida | Verificar quotas no Service Quotas |

### ModelTimeoutException

| Sintoma | Causa | Ação |
|---------|-------|------|
| Modelo não responde | Modelo sobrecarregado ou prompt muito longo | Reduzir `maxTokens` ou simplificar prompt |
| Latência > 20s consistentemente | Modelo inadequado para POC | Considerar modelo mais rápido |

### Região incorreta

| Sintoma | Causa | Ação |
|---------|-------|------|
| Modelo não encontrado mas existe | Região diferente configurada | Confirmar `AWS_REGION=us-east-1` |
| Inference profile não encontrado | Profile disponível em outra região | Verificar disponibilidade regional |

### Model access não habilitado

| Sintoma | Causa | Ação |
|---------|-------|------|
| AccessDenied mesmo com IAM correto | Modelo requer habilitação no console | Abrir Model access e habilitar |
| EULA não aceita | Modelos Anthropic/Meta requerem aceite | Aceitar termos no console |

---

## O que NÃO fazer

- ❌ Escolher um modelo sem testar resposta em português
- ❌ Inventar preço ou latência sem verificação real
- ❌ Usar wildcard no IAM sem tentar ARN específico primeiro
- ❌ Assumir que o modelo está habilitado sem verificar
- ❌ Registrar mensagens ou respostas em documentos compartilhados
- ❌ Usar model ID de documentação sem confirmar na conta
- ❌ Configurar IAM da Lambda com permissões de discovery (ListFoundationModels)
- ❌ Ignorar diferença entre foundation model e inference profile

---

## Como confirmar que está correto

✅ `aws bedrock get-foundation-model --model-identifier <ID>` retorna sem erro
✅ `aws bedrock-runtime converse --model-id <ID> ...` retorna texto em português
✅ Smoke test (`scripts/smoke_test_bedrock.ps1`) exit code 0
✅ Latência medida < 20s (P99)
✅ IAM policy contém ARN específico (ou wildcard documentado)
✅ Model ID registrado em `docs/model-selection-evidence.md` com data e evidências
