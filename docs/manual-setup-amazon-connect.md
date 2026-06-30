# Guia Operacional — Configuração Manual do Amazon Connect

## Objetivo

Este guia descreve todos os passos manuais necessários para configurar o Amazon Connect para a POC-01 (Connect + Bedrock Converse API). Cobre desde a criação do Contact Flow até o teste completo do chat.

**Princípio fundamental: NENHUMA ação deste guia altera a POC MCP original.**

---

## 1. Isolamento obrigatório

### Regras absolutas

| Regra | Descrição |
|-------|-----------|
| ❌ NUNCA editar o Contact Flow ativo da POC MCP | O flow MCP deve permanecer inalterado |
| ✅ Criar novo Contact Flow OU copiar o existente | Sempre com nome prefixado com "bedrock" |
| ✅ Usar nome com prefixo Bedrock | Ex: `connect-bedrock-poc-chat-flow` |
| ✅ Confirmar instância correta | Instância do Amazon Connect onde a POC será executada |
| ✅ Confirmar região correta | `us-east-1` |
| ❌ NUNCA apontar o widget MCP para o flow Bedrock | Widgets devem ser independentes |
| ❌ NUNCA publicar flow sem revisar Lambda associada | Evitar associação acidental com Lambda MCP |

### Verificação antes de começar

- [ ] Sei qual é a instância do Amazon Connect
- [ ] Sei qual é o Contact Flow da POC MCP (para NÃO editá-lo)
- [ ] Conheço o ARN da Lambda Initializer da POC Bedrock
- [ ] Estou na região `us-east-1`

---

## 2. Componentes reaproveitados conceitualmente

Os seguintes componentes existem na POC MCP e serão **replicados** (não compartilhados) na POC Bedrock:

| Componente | POC MCP | POC Bedrock |
|-----------|---------|-------------|
| Chat Widget | Widget apontando para flow MCP | **Novo** widget apontando para flow Bedrock |
| Contact Flow | `connect-mcp-poc-chat-flow` | **Novo:** `connect-bedrock-poc-chat-flow` |
| Initializer Lambda | `connect-mcp-poc-dev-initializer` | `connect-bedrock-poc-dev-initializer` |
| SNS Topic | `connect-mcp-poc-dev-streaming` | `connect-bedrock-poc-dev-streaming` |
| SQS Queue | `connect-mcp-poc-dev-messages` | `connect-bedrock-poc-dev-messages` |
| Integrator Lambda | `connect-mcp-poc-dev-integrator` | `connect-bedrock-poc-dev-integrator` |

> Cada POC tem seus próprios recursos. Não há compartilhamento de filas, tópicos ou tabelas.

---

## 3. Criar ou duplicar Contact Flow

### Passos

1. Abrir o **Amazon Connect** no console AWS
2. Selecionar a instância correta
3. No painel lateral, navegar até **"Routing"** → **"Contact flows"** (o nome pode variar conforme a versão atual do console)
4. Opções:
   - **Opção A — Duplicar:** Localizar o flow da POC MCP, clicar em ações e selecionar "Clone" ou "Duplicate" (se disponível)
   - **Opção B — Criar novo:** Clicar em "Create contact flow" e configurar manualmente
5. Renomear para: `connect-bedrock-poc-chat-flow`
6. **NÃO publicar** até revisar todos os blocos

### Valores a registrar

| Item | Valor |
|------|-------|
| Nome do flow | `connect-bedrock-poc-chat-flow` |
| ID do flow | (gerado após criação) |
| ARN do flow | (gerado após publicação) |
| Instância Connect | (nome da instância) |

---

## 4. Configurar Invoke AWS Lambda Function

### Selecionar a Lambda correta

1. No editor de flow, localizar ou adicionar o bloco **"Invoke AWS Lambda function"** (o nome pode variar)
2. Selecionar a Lambda **Initializer da POC Bedrock**: `connect-bedrock-poc-dev-initializer`

> ⚠️ **CUIDADO:** NÃO selecionar a Lambda `connect-mcp-poc-dev-initializer`. Os nomes são similares. Confirmar o prefixo `connect-bedrock-poc`.

### Configuração do bloco

| Parâmetro | Valor | Notas |
|-----------|-------|-------|
| Execução | Síncrona | O flow aguarda resposta da Lambda |
| Timeout | 8 segundos | Deve ser >= timeout da Lambda Initializer |
| Response validation | Selecionar validação | Para verificar retorno |

### Verificar resposta da Lambda

A Lambda Initializer retorna atributos via `$.External`. O flow deve verificar:

| Atributo | Valor esperado |
|----------|----------------|
| `$.External.Status` | `SUCCESS` |

> ⚠️ **Pegadinha conhecida:** O valor deve ser comparado como **`SUCCESS`** (com dois S no final). Um erro comum é digitar `SUCESS` (com um S). A comparação é case-sensitive e exata.

---

## 5. Configurar lógica do flow

### Estrutura recomendada dos blocos

```
[Set logging behavior]
    ↓
[Set contact attributes - locale pt-BR]
    ↓
[Invoke AWS Lambda function - Initializer Bedrock]
    ↓
[Check contact attributes]
    ├── status == "SUCCESS" → [Wait] → [Disconnect]
    ├── No Match → [Play prompt - Erro] → [Disconnect]
    └── Error → [Play prompt - Erro] → [Disconnect]
```

### Bloco Check contact attributes

| Configuração | Valor |
|-------------|-------|
| Namespace | External |
| Attribute | Status |
| Condition | Equals |
| Value | `SUCCESS` |

### Bloco Wait (após sucesso)

O bloco Wait mantém o chat aberto para receber mensagens do usuário. O streaming via SNS/SQS cuida do processamento.

### Mensagem de erro

Para os branches Error e No Match, configurar uma mensagem amigável:
> "Desculpe, não foi possível iniciar o atendimento. Por favor, tente novamente em alguns instantes."

---

## 6. Configurar streaming

### Como funciona

1. A Lambda Initializer chama `StartContactStreaming` ao receber o contato
2. `StartContactStreaming` configura o Amazon Connect para publicar eventos no **SNS Topic**
3. O SNS Topic publica para a **SQS Queue**
4. A **Lambda Integrator** consome da fila SQS

### Verificações obrigatórias

- [ ] O SNS Topic configurado na Initializer é o da POC **Bedrock** (não MCP)
  - Variável de ambiente `SNS_TOPIC_ARN` na Lambda Initializer
  - Deve conter `connect-bedrock-poc` no nome
- [ ] A SQS Queue subscrita no SNS é a da POC **Bedrock**
- [ ] O event source mapping SQS → Lambda aponta para a Integrator **Bedrock**
- [ ] Os eventos estão chegando (verificar métricas do SQS)

### Confirmar que NÃO é o topic MCP

```powershell
# Verificar env var da Initializer Bedrock
aws lambda get-function-configuration \
  --function-name connect-bedrock-poc-dev-initializer \
  --region us-east-1 \
  --query "Environment.Variables.SNS_TOPIC_ARN" \
  --output text
# Resultado deve conter "connect-bedrock-poc"
```

---

## 7. Associar Lambda à instância do Connect

### Por que é necessário

O Amazon Connect só permite que Contact Flows invoquem Lambdas previamente associadas à instância.

### Passos

1. No console do Amazon Connect, acessar a configuração da instância
2. Navegar até **"AWS Lambda"** ou **"Lambdas"** (o nome pode variar conforme a versão atual do console)
3. Adicionar a Lambda: `connect-bedrock-poc-dev-initializer`
4. Confirmar o ARN correto

### Verificações

- [ ] O ARN contém `connect-bedrock-poc` (não `connect-mcp-poc`)
- [ ] A Lambda aparece na lista de funções associadas
- [ ] A Lambda está disponível no dropdown do bloco Invoke Lambda do flow

> ⚠️ Se a Lambda não aparecer no editor de flow, ela não foi associada corretamente à instância.

---

## 8. Widget de chat

### Criar ou duplicar configuração

1. No painel do Amazon Connect, procurar por **"Chat"**, **"Communication widget"** ou equivalente (o nome pode variar)
2. Criar nova configuração de widget OU duplicar a existente
3. Configurar:
   - **Nome:** `connect-bedrock-poc-widget`
   - **Contact Flow:** Selecionar `connect-bedrock-poc-chat-flow`
   - **Allowed domains:** Incluir domínio de teste (ex: `http://localhost:*`, domínio de staging)
4. Obter o snippet de embed (HTML/JS)

### Regras de isolamento

- O widget da POC MCP deve continuar apontando para o flow MCP
- O widget da POC Bedrock deve apontar para o flow Bedrock
- Se testar ambos simultaneamente, usar abas ou browsers diferentes

### Teste local

1. Criar arquivo HTML mínimo com o snippet do widget Bedrock
2. Servir localmente (ex: `python -m http.server 8080`)
3. Abrir no browser e verificar que o chat abre
4. Verificar que o Contact Flow invocado é o Bedrock (não MCP)

---

## 9. Publicar o Contact Flow

### Antes de publicar

Revisar obrigatoriamente:

- [ ] Nome do flow contém "bedrock" (não "mcp")
- [ ] Bloco Invoke Lambda aponta para `connect-bedrock-poc-dev-initializer`
- [ ] Check contact attributes compara com `SUCCESS` (não `SUCESS`)
- [ ] Branches de erro têm mensagem amigável
- [ ] Wait block está configurado corretamente
- [ ] Disconnect está nos branches corretos

### Publicar

1. Clicar em **"Publish"** ou **"Save and publish"** (o nome pode variar)
2. Confirmar publicação

### Valores a registrar após publicação

| Item | Valor |
|------|-------|
| Contact Flow ARN | (copiar do console) |
| Contact Flow ID | (extrair do ARN ou URL) |
| Data de publicação | YYYY-MM-DD |
| Lambda associada | `connect-bedrock-poc-dev-initializer` |

### Confirmar que NÃO é o flow MCP

```powershell
# Verificar flow existente da MCP (deve continuar inalterado)
aws connect describe-contact-flow \
  --instance-id <INSTANCE_ID> \
  --contact-flow-id <MCP_FLOW_ID> \
  --region us-east-1 \
  --query "ContactFlow.Name" \
  --output text
# Deve retornar o nome do flow MCP (inalterado)
```

---

## 10. Teste operacional

### Sequência de validação

1. **Abrir widget** — verificar que o chat abre sem erro
2. **Iniciar chat** — verificar que o Contact Flow executa
3. **Enviar pergunta** — ex: "Qual é a capital do Brasil?"
4. **Verificar logs da Initializer** — CloudWatch log group `connect-bedrock-poc-dev-initializer`
   - Status: SUCCESS
   - StartContactStreaming OK
5. **Verificar SNS** — métricas do topic (NumberOfMessagesPublished)
6. **Verificar SQS** — métricas da queue (NumberOfMessagesSent)
7. **Verificar Integrator** — CloudWatch log group `connect-bedrock-poc-dev-integrator`
   - Mensagem recebida
   - BedrockClient chamado
   - Resposta enviada
8. **Verificar resposta no chat** — texto em português no widget
9. **Buscar por correlation_id** — usar o ID nos logs para rastrear ponta a ponta

### Comandos úteis

```powershell
# Verificar logs recentes da Initializer
aws logs tail /aws/lambda/connect-bedrock-poc-dev-initializer \
  --region us-east-1 --since 5m

# Verificar logs recentes do Integrator
aws logs tail /aws/lambda/connect-bedrock-poc-dev-integrator \
  --region us-east-1 --since 5m

# Buscar por correlation_id específico
aws logs filter-log-events \
  --log-group-name /aws/lambda/connect-bedrock-poc-dev-integrator \
  --region us-east-1 \
  --filter-pattern '{ $.correlation_id = "<UUID>" }'
```

---

## 11. Checklist de validação

Após completar todos os passos, confirmar:

- [ ] Contact Flow separado criado (nome com "bedrock")
- [ ] Lambda Initializer correta associada (`connect-bedrock-poc-dev-initializer`)
- [ ] Check attributes: status == `SUCCESS` (não SUCESS)
- [ ] Timeout do bloco Invoke Lambda: 8s
- [ ] SNS Topic correto na Initializer (prefixo `connect-bedrock-poc`)
- [ ] SQS Queue correta subscrita no SNS
- [ ] Integrator Lambda Bedrock processando mensagens
- [ ] Widget apontando para flow Bedrock
- [ ] **POC MCP continua funcionando** (testar chat MCP separadamente)
- [ ] Nenhum recurso com nome `connect-mcp-poc` foi alterado

---

## 12. Troubleshooting

### Chat não inicia

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Widget não abre | Domínio não permitido | Adicionar domínio em allowed domains |
| Widget abre mas chat falha | Contact Flow não publicado | Publicar o flow |
| Widget abre mas timeout | Lambda não associada à instância | Associar Lambda |

### Initializer sem logs

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Nenhum log no CloudWatch | Lambda não está sendo invocada | Verificar associação com instância Connect |
| Lambda não existe | Deploy não executado | Executar deploy da infra |
| Permissão insuficiente | Role da Lambda sem connect:* | Verificar IAM |

### Lambda não aparece no flow editor

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Dropdown vazio ou sem a Lambda | Lambda não associada à instância | Seção 7 deste guia |
| Lambda com nome errado | ARN incorreto | Verificar nome exato |
| Região diferente | Lambda em outra região | Confirmar us-east-1 |

### Erro no Invoke Lambda

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| "Function error" no flow | Exceção na Lambda | Verificar logs da Initializer |
| Timeout no bloco | Lambda demora > 8s | Verificar cold start, aumentar memória |
| "Function not found" | ARN inválido ou Lambda deletada | Verificar se Lambda existe |

### Status sem match

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Flow vai para "No Match" | Lambda retorna valor diferente | Verificar retorno exato da Lambda |
| `SUCESS` vs `SUCCESS` | Typo no check attributes | Corrigir para `SUCCESS` (dois S) |
| Case sensitivity | Minúsculas vs maiúsculas | Comparação é case-sensitive |

### Streaming não inicia

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| SNS sem eventos | `StartContactStreaming` falhou | Verificar logs da Initializer |
| SNS com erro | Permissão SNS insuficiente | Verificar policy do SNS topic |
| Eventos no SNS mas não no SQS | Subscription não configurada | Verificar SNS → SQS subscription |

### SQS vazia

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Fila sem mensagens | SNS não publicando | Verificar seção anterior |
| Mensagens consumidas imediatamente | Integrator processando rápido (normal) | Verificar logs do Integrator |
| Event source mapping desabilitado | Mapping disabled | Habilitar mapping |

### Integrator sem logs

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Nenhum log | Event source mapping desabilitado | Habilitar |
| Lambda não existe | Deploy incompleto | Executar deploy |
| SQS diferente | Mapping aponta para fila errada | Verificar event source ARN |

### Resposta "Desculpe"

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Mensagem genérica de erro | BedrockFatalError | Verificar logs do Integrator por error_code |
| Mensagem de fallback | Modelo retornou vazio | Verificar model ID e system prompt |
| AccessDeniedException nos logs | IAM incorreto | Revisar policy com `bedrock:InvokeModel` |

### Token expirado

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Resposta não chega | ConnectionToken expirado | Verificar renovação nos logs |
| "TOKEN_EXPIRED" nos logs | Sessão muito longa | Verificar TTL e renovação |
| Renovação falha | ParticipantToken inválido | Verificar Initializer e persistência |

### Flow não publicado

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Chat não funciona | Versão draft ativa | Publicar o flow |
| Mudanças não refletem | Publicação pendente | Re-publicar após edições |

### Widget apontando para flow errado

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Resposta vem do MCP | Widget usa flow MCP | Reconfigurar widget para flow Bedrock |
| Ambos os flows respondem | Confusão de widgets | Verificar Contact Flow ID no snippet |

---

## O que NÃO fazer

- ❌ Editar o Contact Flow da POC MCP
- ❌ Redirecionar o widget MCP para o flow Bedrock
- ❌ Usar o mesmo SNS Topic para ambas as POCs
- ❌ Associar Lambda MCP ao flow Bedrock
- ❌ Publicar flow sem revisar Lambda associada
- ❌ Deletar ou desassociar Lambda da POC MCP
- ❌ Alterar configurações da instância Connect que afetem a POC MCP
- ❌ Usar `terraform destroy` em recursos da POC MCP

---

## Como confirmar que está correto

✅ Contact Flow com nome `connect-bedrock-poc-*` publicado
✅ Lambda `connect-bedrock-poc-dev-initializer` associada e invocada
✅ Status `SUCCESS` retornado pela Initializer
✅ Eventos aparecendo no SNS topic `connect-bedrock-poc-*`
✅ Mensagens chegando na SQS queue `connect-bedrock-poc-*`
✅ Integrator `connect-bedrock-poc-dev-integrator` processando
✅ Resposta em português recebida no chat
✅ Correlation ID rastreável nos logs ponta a ponta
✅ POC MCP funciona normalmente em paralelo (testar separadamente)
✅ Nenhum recurso `connect-mcp-poc-*` foi alterado
