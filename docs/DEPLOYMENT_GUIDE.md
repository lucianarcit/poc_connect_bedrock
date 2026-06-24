# Manual Completo de Implantação — POC Amazon Connect + MCP

> **Status:** Implementação concluída; `terraform fmt/validate/plan` pendentes.
> **Última atualização:** Junho 2026
> **Ambiente de referência:** Windows 11, PowerShell, AWS CLI v2, Terraform >= 1.6

---

## A. Visão Geral da Arquitetura

### Fluxo real da POC

```
Cliente (browser)
  → Hosted Chat Widget
    → Amazon Connect Contact Flow
      → Lambda Initializer (invocada pelo bloco "Invoke AWS Lambda")
        → connect:StartContactStreaming → SNS Topic
        → connect:CreateParticipant (CUSTOM_BOT)
        → connectparticipant:CreateParticipantConnection
        → DynamoDB Sessions (tokens criptografados com KMS)
      → Contact Flow mantém sessão ativa

Mensagens do chat:
  → Amazon Connect Chat Streaming
    → SNS Topic (connect-mcp-poc-dev-streaming)
      → SQS Queue (connect-mcp-poc-dev-messages)
        → Lambda Integrator (event source mapping, batch_size=5)
          → DynamoDB Idempotency (lease-based)
          → DynamoDB Sessions (busca token)
          → KMS Decrypt (ConnectionToken)
          → Lambda Function URL (MCP Server, via SigV4)
            → FastMCP + Mangum → tool search/procedure/health
          → connectparticipant:SendMessage (ConnectionToken)
          → Resposta aparece no chat do cliente

Falhas:
  → SQS VisibilityTimeout (360s) → retry
  → maxReceiveCount (3) → DLQ (connect-mcp-poc-dev-messages-dlq)
  → FAILED_FINAL → CloudWatch Metric Filter → Alarme
```

### Tabela de componentes

| Componente | Criado por | Finalidade | Onde configurar |
|------------|-----------|------------|-----------------|
| Instância Amazon Connect | MANUAL | Plataforma de chat | Console AWS → Amazon Connect |
| Contact Flow | MANUAL | Orquestra o chat, invoca Initializer | Console Amazon Connect |
| Hosted Chat Widget | MANUAL | Interface do usuário no browser | Console Amazon Connect |
| Lambda Initializer | AUTOMÁTICO (Terraform) | Registra bot no contato | `terraform/lambda.tf` |
| Lambda Integrator | AUTOMÁTICO (Terraform) | Processa mensagens, chama MCP | `terraform/lambda.tf` |
| Lambda MCP Server | AUTOMÁTICO (Terraform) | Servidor MCP fictício | `terraform/lambda.tf` |
| Function URL (MCP) | AUTOMÁTICO (Terraform) | Endpoint HTTPS com AWS_IAM | `terraform/function_url.tf` |
| DynamoDB Sessions | AUTOMÁTICO (Terraform) | Sessões e tokens criptografados | `terraform/dynamodb.tf` |
| DynamoDB Idempotency | AUTOMÁTICO (Terraform) | Controle de duplicidade | `terraform/dynamodb.tf` |
| KMS Key | AUTOMÁTICO (Terraform) | Criptografia de tokens | `terraform/kms.tf` |
| SNS Topic | AUTOMÁTICO (Terraform) | Streaming de mensagens Connect | `terraform/sns.tf` |
| SQS Queue | AUTOMÁTICO (Terraform) | Buffer de mensagens | `terraform/sqs.tf` |
| SQS DLQ | AUTOMÁTICO (Terraform) | Mensagens com falha persistente | `terraform/sqs.tf` |
| Event Source Mapping | AUTOMÁTICO (Terraform) | SQS → Lambda Integrator | `terraform/event_source.tf` |
| IAM Roles (3) | AUTOMÁTICO (Terraform) | Permissões das Lambdas | `terraform/iam.tf` |
| CloudWatch Log Groups | AUTOMÁTICO (Terraform) | Logs das Lambdas | `terraform/monitoring.tf` |
| Metric Filter | AUTOMÁTICO (Terraform) | Captura FailedFinal | `terraform/monitoring.tf` |
| Alarmes (6) | AUTOMÁTICO (Terraform) | Alertas operacionais | `terraform/monitoring.tf` |
| Autorização Lambda no Connect | MANUAL | Permite Contact Flow invocar Lambda | Console Amazon Connect |

---

## B. O que o Terraform Cria

### Lambda Functions (`terraform/lambda.tf`)

| Recurso Terraform | Nome | Handler | Timeout | Variável | Output |
|-------------------|------|---------|---------|----------|--------|
| `aws_lambda_function.initializer` | `connect-mcp-poc-{env}-initializer` | `initializer.handler.handler` | 8s | `initializer_timeout` | `initializer_lambda_arn` |
| `aws_lambda_function.integrator` | `connect-mcp-poc-{env}-integrator` | `integrator.handler.handler` | 60s | `integrator_timeout` | `integrator_lambda_arn` |
| `aws_lambda_function.mcp_server` | `connect-mcp-poc-{env}-mcp-server` | `mcp_server.handler.handler` | 30s | `mcp_server_timeout` | `mcp_server_lambda_arn` |

### IAM (`terraform/iam.tf`)

| Recurso | Nome | Principal | Ações-chave |
|---------|------|-----------|-------------|
| `aws_iam_role.initializer` | `...-initializer-role` | lambda.amazonaws.com | DynamoDB Sessions, KMS Encrypt, connect:StartContactStreaming, connect:CreateParticipant |
| `aws_iam_role.integrator` | `...-integrator-role` | lambda.amazonaws.com | SQS, DynamoDB (2 tabelas), KMS, lambda:InvokeFunctionUrl, lambda:InvokeFunction |
| `aws_iam_role.mcp_server` | `...-mcp-server-role` | lambda.amazonaws.com | Apenas AWSLambdaBasicExecutionRole (logs) |

### DynamoDB (`terraform/dynamodb.tf`)

| Recurso | Nome | PK | TTL | Criptografia | Output |
|---------|------|----|-----|-------------|--------|
| `aws_dynamodb_table.sessions` | `connect-mcp-poc-{env}-sessions` | `pk` (S) | `expires_at` | Default (aws/dynamodb) | `sessions_table_name` |
| `aws_dynamodb_table.idempotency` | `connect-mcp-poc-{env}-idempotency` | `pk` (S) | `expires_at` | Default (aws/dynamodb) | `idempotency_table_name` |

### KMS (`terraform/kms.tf`)

| Recurso | Alias | Rotação | Deletion Window | Output |
|---------|-------|---------|-----------------|--------|
| `aws_kms_key.tokens` | `alias/connect-mcp-poc-{env}-tokens` | Sim | 7 dias | `kms_key_arn` |

### SNS (`terraform/sns.tf`)

| Recurso | Nome | Subscription | Output |
|---------|------|-------------|--------|
| `aws_sns_topic.streaming` | `connect-mcp-poc-{env}-streaming` | → SQS (raw=false) | `sns_topic_arn` |

### SQS (`terraform/sqs.tf`)

| Recurso | Nome | Visibility | Retenção | DLQ | Output |
|---------|------|-----------|----------|-----|--------|
| `aws_sqs_queue.messages` | `...-messages` | 360s | 4 dias | → dlq (max 3) | `sqs_queue_url` |
| `aws_sqs_queue.dlq` | `...-messages-dlq` | — | 14 dias | — | `sqs_dlq_url` |

### Function URL (`terraform/function_url.tf`)

| Recurso | Auth Type | CORS | Output |
|---------|-----------|------|--------|
| `aws_lambda_function_url.mcp_server` | `AWS_IAM` | Vazio (server-to-server) | `mcp_server_function_url` |

### Event Source Mapping (`terraform/event_source.tf`)

| Recurso | Source | Function | Batch | Response |
|---------|--------|----------|-------|----------|
| `aws_lambda_event_source_mapping.sqs_to_integrator` | SQS messages | Integrator | 5 | ReportBatchItemFailures |

### Monitoring (`terraform/monitoring.tf`)

| Recurso | Nome | Condição | Ação |
|---------|------|----------|------|
| Log Group Initializer | `/aws/lambda/...-initializer` | — | — |
| Log Group Integrator | `/aws/lambda/...-integrator` | — | — |
| Log Group MCP Server | `/aws/lambda/...-mcp-server` | — | — |
| Metric Filter | `...-failed-final` | `{ $.metric = "FailedFinal" }` | → FailedFinalCount |
| Alarm `failed_final` | `...-failed-final` | Sum > 0 / 5min | SNS alarmes |
| Alarm `dlq_messages` | `...-dlq-not-empty` | Visible > 0 | SNS alarmes |
| Alarm `initializer_errors` | `...-initializer-errors` | Sum > 2 / 10min | SNS alarmes |
| Alarm `integrator_errors` | `...-integrator-errors` | Sum > 2 / 10min | SNS alarmes |
| Alarm `integrator_throttles` | `...-integrator-throttles` | Sum > 0 / 5min | SNS alarmes |
| Alarm `sqs_oldest_message` | `...-sqs-oldest-message` | Max > 300s | SNS alarmes |

---

## C. O que Precisa Ser Feito Manualmente

> ⚠️ **Os itens abaixo NÃO são criados pelo Terraform desta POC.**

### C.1 Criar a Instância Amazon Connect

- **Serviço:** Amazon Connect
- **Console:** AWS Console → Amazon Connect → Create instance
- **Caminho:** `https://console.aws.amazon.com/connect/`
- **Passos:**
  1. Clicar em "Add an instance"
  2. Escolher "Store users within Amazon Connect"
  3. Definir o alias (ex: `mcp-poc-dev`)
  4. Criar usuário admin
  5. Aceitar padrões de telefonia (não usamos voz)
  6. Aceitar padrões de armazenamento
  7. Confirmar e criar
- **Valores a guardar:**
  - Instance ID: `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee`
  - Instance ARN: `arn:aws:connect:<region>:<account>:instance/<id>`
  - Região: deve ser **a mesma** do Terraform (`aws_region`)
- **Validação:**
  ```powershell
  aws connect list-instances --region us-east-1
  ```
- **Erro comum:** Criar em região diferente da configurada no Terraform.

### C.2 Autorizar a Lambda Initializer na Instância Connect

- **Serviço:** Amazon Connect
- **Console:** Amazon Connect → Instância → Contact flows → AWS Lambda
- **Caminho:** `https://<alias>.my.connect.aws` → Contact flows → AWS Lambda
- **Passos:**
  1. Abrir a instância Connect
  2. Menu lateral: "Contact flows"
  3. Seção "AWS Lambda"
  4. Colar o ARN da Lambda Initializer (obtido do output `initializer_lambda_arn`)
  5. Clicar "Add Lambda Function"
- **Valor:** `arn:aws:lambda:<region>:<account>:function:connect-mcp-poc-dev-initializer`
- **Como obter:** `terraform output initializer_lambda_arn`
- **Validação:** O ARN aparece na lista de funções autorizadas.
- **Erro comum:** Colar ARN com versão/alias ($LATEST), ou Lambda em região diferente.

### C.3 Criar o Contact Flow de Chat

- **Serviço:** Amazon Connect
- **Console:** Amazon Connect → Routing → Contact flows → Create contact flow
- **Passos:**
  1. Nome: `MCP-POC-Chat-Flow`
  2. Tipo: "Contact flow" (não "Customer queue flow")
  3. Adicionar bloco **"Invoke AWS Lambda Function"**
     - Selecionar: `connect-mcp-poc-dev-initializer`
     - Timeout: `8` segundos
  4. Ramificação **Success**:
     - Adicionar bloco **"Wait"** (Loop → tempo ou condição de encerramento)
     - Ou adicionar bloco **"Transfer to queue"** se handoff necessário
  5. Ramificação **Error**:
     - Adicionar bloco **"Play prompt"** ou **"Disconnect"**
  6. Publicar o fluxo (botão "Publish")
- **Valor a guardar:** Contact Flow ID (visível na URL ou ARN)
- **Validação:** O fluxo aparece como "Published" na lista.
- **Erro comum:** Não publicar o fluxo (fica em "Draft" e não funciona).

### C.4 Criar e Configurar o Hosted Chat Widget

- **Serviço:** Amazon Connect
- **Console:** Amazon Connect → Channels → Chat → Communication Widget
- **Passos:**
  1. Criar novo widget
  2. Associar ao Contact Flow criado (`MCP-POC-Chat-Flow`)
  3. Configurar domínios permitidos:
     - Para teste local: `http://localhost:8080`
     - Para produção: domínio real
  4. Copiar o snippet JavaScript gerado
  5. Incorporar em uma página HTML de teste
- **Validação:** Widget abre no browser e conecta ao chat.
- **Erro comum:** Domínio de origem não permitido (widget não carrega).

### C.5 Confirmar Subscription de E-mail (Alarmes)

Se `alarm_email` foi preenchido no `terraform.tfvars`:
- O Terraform cria uma subscription SNS com protocolo "email"
- A AWS envia um e-mail de confirmação para o endereço
- **Ação manual:** Clicar no link "Confirm subscription" no e-mail
- **Validação:** Status da subscription muda de "Pending" para "Confirmed"
- Sem confirmação, os alarmes não enviam notificações.

---

## D. Checklist de Pré-requisitos

- [ ] Repositório clonado e branch correta (ex: `main`)
- [ ] Python 3.12+ instalado (`python --version`)
- [ ] Ambiente virtual `.venv` criado e ativado
- [ ] Dependências de dev instaladas (`pip install -r requirements-dev.txt`)
- [ ] AWS CLI v2 instalada (`aws --version`)
- [ ] Terraform >= 1.6 instalado (`terraform -version`)
- [ ] Autenticação AWS válida (`aws sts get-caller-identity`)
- [ ] Conta AWS confirmada (verificar account ID)
- [ ] Região confirmada (`aws configure list`)
- [ ] Permissões suficientes (admin ou IAM com acesso a Lambda, DynamoDB, KMS, SQS, SNS, Connect, CloudWatch)
- [ ] Instância Amazon Connect criada na mesma região
- [ ] Connect Instance ID e ARN disponíveis
- [ ] ZIPs das Lambdas gerados (`.\scripts\build_lambdas.ps1`)
- [ ] Testes locais passando (`python -m pytest`)
- [ ] `terraform fmt` executado sem alterações
- [ ] `terraform init` executado com sucesso
- [ ] `terraform validate` passando
- [ ] `terraform plan` revisado e aprovado
- [ ] Aprovação explícita do responsável antes do apply

### Comandos de verificação (seguros — apenas consulta)

```powershell
terraform -version
aws --version
python --version
aws sts get-caller-identity
aws configure list
aws connect list-instances --region us-east-1
git status
```

---

## E. Preparação da Máquina Windows

### E.1 Abrir PowerShell e entrar no projeto

```powershell
cd C:\proj\poc_connect
```

### E.2 Criar e ativar ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### E.3 Instalar dependências de desenvolvimento

```powershell
pip install -r requirements-dev.txt
```

### E.4 Executar testes

```powershell
python -m pytest
```

Resultado esperado: `241 passed`, cobertura ≥ 80%.

### E.5 Executar build das Lambdas

```powershell
.\scripts\build_lambdas.ps1
```

Resultado esperado:
```
initializer.zip - ~2.5 MB
integrator.zip  - ~3.1 MB
mcp_server.zip  - ~4.5 MB
```

### E.6 Verificar ZIPs gerados

```powershell
Get-ChildItem packages\*.zip | Select-Object Name, @{N="MB";E={[math]::Round($_.Length/1MB,2)}}
```

### E.7 Verificar que packages/ está no .gitignore

```powershell
Select-String -Path .gitignore -Pattern "packages/"
```

---

## F. Criação e Preenchimento do terraform.tfvars

### F.1 Copiar o template

```powershell
cd terraform
Copy-Item terraform.tfvars.example terraform.tfvars
```

> ⚠️ **NUNCA faça commit de `terraform.tfvars` com dados reais.** Ele já está no `.gitignore`.

### F.2 Tabela de variáveis

| Variável | Obrigatória | Exemplo | Como obter | Sensível |
|----------|------------|---------|-----------|----------|
| `aws_region` | Não (default: us-east-1) | `us-east-1` | Escolha da equipe | Não |
| `environment_name` | Não (default: dev) | `dev` | Escolha da equipe | Não |
| `connect_instance_id` | **Sim** | `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee` | `aws connect list-instances` | Não |
| `connect_instance_arn` | **Sim** | `arn:aws:connect:us-east-1:123456789012:instance/aaa...` | `aws connect list-instances` | Não |
| `connect_contact_flow_id` | Não | `""` | Console Connect após criar flow | Não |
| `alarm_email` | Não | `""` | E-mail da equipe | Sim (PII) |
| `log_retention_days` | Não (default: 14) | `14` | Política de retenção | Não |
| `tags` | Não | `{Team="platform"}` | Padrão da organização | Não |

### F.3 Comandos para descobrir Instance ID e ARN

```powershell
aws connect list-instances --region us-east-1 --output table
```

### F.4 Exemplo completo (apenas placeholders)

```hcl
aws_region              = "us-east-1"
environment_name        = "dev"
connect_instance_id     = "COLOQUE-SEU-INSTANCE-ID-AQUI"
connect_instance_arn    = "arn:aws:connect:us-east-1:CONTA:instance/COLOQUE-SEU-INSTANCE-ID-AQUI"
connect_contact_flow_id = ""
alarm_email             = ""
log_retention_days      = 14

tags = {
  Team  = "platform"
  Owner = "seu-nome"
}
```

---

## G. Fluxo Terraform Seguro

### G.1 Sequência obrigatória

```powershell
cd C:\proj\poc_connect\terraform

# 1. Formata (não altera lógica, apenas estilo)
terraform fmt -recursive

# 2. Baixa providers e inicializa backend
terraform init

# 3. Valida configuração (sem acessar AWS)
terraform validate

# 4. Mostra alterações planejadas (consulta AWS, NÃO altera nada)
terraform plan -out=tfplan

# 5. Revisar o plano detalhado
terraform show tfplan
```

### G.2 Checklist pré-apply

- [ ] Conta AWS correta (verificar account ID no plan)
- [ ] Região correta (mesma do Connect)
- [ ] Nenhuma exclusão inesperada no plan
- [ ] Quantidade de recursos coerente (~30 recursos na primeira execução)
- [ ] Nenhum segredo aparecendo no plan
- [ ] Connect Instance ARN correto
- [ ] Lambda ZIPs existem em `packages/`
- [ ] Custos entendidos (ver seção N)
- [ ] Plano revisado por responsável

### G.3 Apply (⚠️ DESTRUTIVO — cria recursos AWS com custo)

> ⚠️ **Este comando CRIA RECURSOS NA AWS e pode gerar custos.**
> Execute somente após revisão e aprovação do plan.

```powershell
terraform apply tfplan
```

**Não use** `-auto-approve` no fluxo recomendado.

### G.4 Verificar outputs após apply

```powershell
terraform output
```

Outputs disponíveis:
- `sns_topic_arn` — configurar no Contact Flow (StartContactStreaming)
- `initializer_lambda_arn` — autorizar no Amazon Connect
- `mcp_server_function_url` — URL HTTPS do MCP Server
- `sessions_table_name`, `idempotency_table_name`
- `kms_key_arn`, `sqs_queue_url`, `sqs_dlq_url`

---

## H. Configuração Manual do Amazon Connect Após o Apply

### H.1 Obter outputs do Terraform

```powershell
terraform output initializer_lambda_arn
terraform output sns_topic_arn
terraform output mcp_server_function_url
```

### H.2 Autorizar Lambda na instância Connect

1. Console AWS → Amazon Connect → selecionar instância
2. Menu lateral → "Contact flows"
3. Seção "AWS Lambda" → colar ARN do output `initializer_lambda_arn`
4. Clicar "Add Lambda Function"
5. Verificar que aparece na lista

### H.3 Criar Contact Flow de Chat

1. Abrir painel da instância (link do console Connect)
2. Routing → Contact flows → "Create contact flow"
3. Nome: `MCP-POC-Chat-Flow`
4. Adicionar bloco **"Invoke AWS Lambda Function"**
   - Function ARN: selecionar `connect-mcp-poc-dev-initializer`
   - Timeout: `8` (segundos)
5. Conectar saída "Success" a um bloco **"Wait"**
   - Configurar timeout (ex: 5 minutos) ou condição de saída
6. Conectar saída "Error" a um bloco **"Disconnect"**
7. Clicar **"Publish"**

### H.4 Validar no CloudWatch

Após publicar o flow e testar um chat:
```powershell
# Ver logs da Initializer (substitua região e nome)
aws logs tail "/aws/lambda/connect-mcp-poc-dev-initializer" --since 5m --region us-east-1
```

### H.5 Criar Hosted Chat Widget

1. Amazon Connect → Channels → Chat → "Create widget"
2. Associar ao flow `MCP-POC-Chat-Flow`
3. Domínios permitidos: `http://localhost:8080`
4. Copiar snippet JavaScript

### H.6 Página HTML de teste

Servir localmente (necessário para domínio permitido):

```powershell
python -m http.server 8080
```

Acessar: `http://localhost:8080/test.html`

> **Nota:** Abrir `file://` não funciona — o widget requer origem HTTP.

---

## I. Testes Ponta a Ponta

### Teste 1 — Health check do MCP

- **Entrada no chat:** `qual o status do sistema`
- **Resultado esperado:** Resposta com "Status: healthy" e quantidade de documentos
- **Log esperado:** JSON com `message_id`, `tool_name: health_check`, status `COMPLETED`

### Teste 2 — Pesquisa de documentação

- **Entrada:** `como redefinir minha senha`
- **Resultado esperado:** Resposta com conteúdo do DOC-001 (redefinição de senha)
- **Componentes atravessados:** Widget → Connect → SNS → SQS → Integrator → MCP → Participant Service → Widget

### Teste 3 — Mensagem duplicada

- **Comportamento:** SNS pode entregar a mesma mensagem duas vezes
- **Resultado esperado:** Segunda entrega encontra status `DUPLICATE_COMPLETED` no DynamoDB → ignora silenciosamente
- **Evidência:** Log com "Duplicate completed" e nenhuma segunda resposta no chat

### Teste 4 — Falha transitória

- **Comportamento:** Se MCP Server retorna timeout ou 5xx
- **Resultado esperado:** Item volta para SQS (fail), retry automático após VisibilityTimeout
- **Evidência:** Log com `should_fail=True`, mensagem reaparece na fila

### Teste 5 — DLQ

- **Como provocar:** Desligar ou desconfigurar a Lambda MCP Server (ex: timeout muito baixo)
- **Resultado esperado:** Após 3 falhas consecutivas, mensagem vai para DLQ
- **Verificação:**
  ```powershell
  aws sqs get-queue-attributes --queue-url <DLQ_URL> --attribute-names ApproximateNumberOfMessages --region us-east-1
  ```
- **Alarme:** `connect-mcp-poc-dev-dlq-not-empty` dispara

### Teste 6 — FAILED_FINAL

- **Comportamento:** Erro fatal (ex: JSON-RPC error, tool não existe)
- **Resultado esperado:** Mensagem genérica enviada ao chat (se possível), status `FAILED_FINAL` no DynamoDB, item **removido** da SQS (não vai para DLQ)
- **Evidência:** Metric Filter captura `{ $.metric = "FailedFinal" }` → alarme dispara
- **Diferença para DLQ:** FAILED_FINAL = decisão explícita do código; DLQ = falhas repetidas sem decisão

| Etapa | Onde verificar | Evidência esperada |
|-------|----------------|-------------------|
| Chat abriu | Browser | Widget conectado |
| Initializer executou | CloudWatch `/aws/lambda/...-initializer` | Log "Initialization complete" |
| SNS recebeu | CloudWatch Metrics → SNS | NumberOfMessagesPublished > 0 |
| SQS recebeu | Console SQS | Messages Available > 0 (transitório) |
| Integrator processou | CloudWatch `/aws/lambda/...-integrator` | Log com contact_id e status |
| MCP respondeu | CloudWatch `/aws/lambda/...-mcp-server` | Request 200 processado |
| Resposta no chat | Browser | Mensagem do bot aparece |

---

## J. Observabilidade

### Log Groups reais

| Lambda | Log Group |
|--------|-----------|
| Initializer | `/aws/lambda/connect-mcp-poc-dev-initializer` |
| Integrator | `/aws/lambda/connect-mcp-poc-dev-integrator` |
| MCP Server | `/aws/lambda/connect-mcp-poc-dev-mcp-server` |

### Buscar por contact_id

```powershell
aws logs filter-log-events `
  --log-group-name "/aws/lambda/connect-mcp-poc-dev-integrator" `
  --filter-pattern "{ $.contact_id = \"SEU-CONTACT-ID\" }" `
  --region us-east-1
```

### Buscar FailedFinal

```powershell
aws logs filter-log-events `
  --log-group-name "/aws/lambda/connect-mcp-poc-dev-integrator" `
  --filter-pattern "{ $.metric = \"FailedFinal\" }" `
  --region us-east-1
```

### Alarmes criados

| Alarme | Métrica | Limiar |
|--------|---------|--------|
| `connect-mcp-poc-dev-failed-final` | FailedFinalCount (custom) | > 0 em 5min |
| `connect-mcp-poc-dev-dlq-not-empty` | ApproximateNumberOfMessagesVisible | > 0 em 5min |
| `connect-mcp-poc-dev-initializer-errors` | Errors (Lambda) | > 2 em 10min |
| `connect-mcp-poc-dev-integrator-errors` | Errors (Lambda) | > 2 em 10min |
| `connect-mcp-poc-dev-integrator-throttles` | Throttles (Lambda) | > 0 em 5min |
| `connect-mcp-poc-dev-sqs-oldest-message` | AgeOfOldestMessage | > 300s |

### O que NÃO logar

- ❌ ParticipantToken, ConnectionToken (nunca em plaintext)
- ❌ Corpo completo da mensagem do cliente (PII)
- ❌ Credenciais AWS, session tokens
- ❌ Conteúdo descriptografado

---

## K. Troubleshooting

| Sintoma | Causa provável | Onde olhar | Correção |
|---------|---------------|-----------|----------|
| Terraform pede variável interativamente | `terraform.tfvars` incompleto | `terraform/terraform.tfvars` | Preencher variáveis obrigatórias |
| Connect ARN inválido | Formato errado ou conta diferente | `terraform.tfvars` → `connect_instance_arn` | `aws connect list-instances` para obter correto |
| Região diferente entre Connect e Terraform | Instância em us-west-2, Terraform em us-east-1 | `aws_region` vs região da instância | Usar mesma região |
| ZIP inexistente / plan falha | Build não executado | `packages/*.zip` | `.\scripts\build_lambdas.ps1` |
| Handler não encontrado (Runtime.ImportModuleError) | Handler path errado no ZIP | CloudWatch logs da Lambda | Verificar que `initializer/handler.py` existe na raiz do ZIP |
| ModuleNotFoundError no Lambda | Dependência ausente no ZIP | CloudWatch logs | Verificar requirements no build script |
| Wheel Windows dentro do ZIP (.pyd) | Build sem `--platform manylinux2014_x86_64` | Inspecionar ZIP com `zipfile` | Rebuild com script correto |
| AccessDenied no KMS | Role sem kms:Encrypt/Decrypt | CloudWatch logs | Verificar `iam.tf` statements |
| AccessDenied na Function URL (403) | Role sem lambda:InvokeFunctionUrl | CloudWatch Integrator | Verificar IAM do Integrator |
| Erro de assinatura SigV4 (403) | URL não é .lambda-url.*.on.aws ou credenciais inválidas | CloudWatch Integrator | Verificar MCP_SERVER_URL env var |
| Timeout da Initializer (>8s) | Chamadas Connect lentas ou retries | CloudWatch Initializer | Verificar latência das APIs Connect |
| Mensagem chega no SQS mas não processa | Event source mapping desabilitado | Console Lambda → triggers | Habilitar mapping |
| Partial batch response não funciona | Falta `function_response_types` | `event_source.tf` | Verificar `ReportBatchItemFailures` |
| Mensagem vai para DLQ | 3 falhas consecutivas | DLQ messages + CloudWatch | Investigar causa da falha no log |
| FAILED_FINAL sem alarme | Metric Filter não captura | CloudWatch Metrics custom namespace | Verificar pattern `{ $.metric = "FailedFinal" }` |
| Contact Flow chama Lambda errada | ARN incorreto no bloco | Console Connect → Contact Flow | Editar bloco, selecionar Lambda correta |
| Lambda não autorizada no Connect | Falta add no console | Console Connect → Contact flows → AWS Lambda | Adicionar ARN |
| Chat Widget bloqueado por origem | Domínio não permitido | Console do browser (CORS/iframe) | Adicionar domínio no widget config |
| Chat abre mas não responde | Initializer falhou ou streaming não configurado | CloudWatch Initializer | Verificar status=SUCCESS e logs |
| Token expirado | ConnectionToken venceu sem renovação | CloudWatch Integrator → "TOKEN_EXPIRED" | Código renova automaticamente; se falha, verificar ParticipantToken |
| Ausência de logs | Log group sem permissão ou Lambda sem execution role | Console CloudWatch | Verificar AWSLambdaBasicExecutionRole |
| Subscription SNS aguardando confirmação | E-mail de alarme não confirmado | Console SNS → Subscriptions | Clicar link no e-mail |

---

## L. Rollback e Destroy

### Diferença entre rollback e destroy

| Ação | Escopo | Reversibilidade |
|------|--------|-----------------|
| Rollback Connect (manual) | Contact Flow, Widget, autorização Lambda | Totalmente reversível |
| `terraform destroy` | Todos os recursos Terraform | Remove permanentemente |
| Dados DynamoDB | Conteúdo das tabelas | Irrecuperável após destroy |
| KMS Key | Chave de criptografia | 7 dias de waiting period antes de exclusão |
| CloudWatch Logs | Logs existentes | Removidos com o log group |

### Checklist de destruição

> ⚠️ **DESTRUTIVO — Ações abaixo removem recursos permanentemente.**

- [ ] Salvar evidências de teste necessárias (screenshots, logs)
- [ ] Exportar logs do CloudWatch se necessário
- [ ] Verificar DLQ (mensagens pendentes serão perdidas)
- [ ] Remover Hosted Chat Widget (Console Connect)
- [ ] Despublicar ou remover Contact Flow (Console Connect)
- [ ] Remover autorização da Lambda no Connect (Console Connect → Contact flows → AWS Lambda)
- [ ] Executar plan de destruição:
  ```powershell
  cd C:\proj\poc_connect\terraform
  terraform plan -destroy
  ```
- [ ] Revisar o plan (verificar quantidade de recursos a remover)
- [ ] Executar destroy:
  ```powershell
  terraform destroy
  ```
- [ ] Confirmar digitando "yes" quando solicitado
- [ ] Verificar recursos restantes:
  ```powershell
  aws lambda list-functions --region us-east-1 | Select-String "connect-mcp-poc"
  aws dynamodb list-tables --region us-east-1 | Select-String "connect-mcp-poc"
  ```
- [ ] Decidir se a instância Connect manual deve ser removida
  ```powershell
  aws connect delete-instance --instance-id SEU-INSTANCE-ID --region us-east-1
  ```

### Recursos que podem permanecer após destroy

- Instância Amazon Connect (criada manualmente)
- KMS Key em estado "Pending deletion" (7 dias)
- Subscription SNS de e-mail (se não confirmada)

---

## M. Custos e Limpeza

### Serviços com custo potencial

| Serviço | Quando cobra | Como evitar após POC |
|---------|-------------|---------------------|
| Lambda | Por invocação + duração | `terraform destroy` |
| DynamoDB | Por requisição (PAY_PER_REQUEST) | `terraform destroy` |
| KMS | $1/mês por chave ativa | `terraform destroy` (7d waiting) |
| SQS | Por mensagem | `terraform destroy` |
| SNS | Por mensagem publicada | `terraform destroy` |
| CloudWatch Logs | Por ingestão + armazenamento | `terraform destroy` ou ajustar retenção |
| CloudWatch Alarms | Por alarme/mês | `terraform destroy` |
| Amazon Connect | Minutos de uso + telefone (se ativo) | Remover instância manualmente |

### Para evitar custos contínuos após a POC

1. `terraform destroy` — remove todos os recursos Terraform
2. Remover instância Amazon Connect — Console ou CLI
3. Verificar que nenhuma Lambda, tabela ou fila permanece

> **Nota:** Consulte a [Calculadora de Preços AWS](https://calculator.aws/) para estimativas atualizadas. Não informamos preços específicos aqui.

---

## N. Timings Configurados

| Parâmetro | Valor | Variável Terraform | Justificativa |
|-----------|-------|-------------------|---------------|
| Lambda Initializer timeout | 8s | `initializer_timeout` | Contact Flow timeout ~8s |
| Lambda Integrator timeout | 60s | `integrator_timeout` | Processamento MCP + SendMessage |
| Lambda MCP Server timeout | 30s | `mcp_server_timeout` | Tools rápidas na POC |
| Lease de idempotência | 90s | `lease_duration_seconds` | > Lambda timeout (evita conflito) |
| SQS VisibilityTimeout | 360s | `sqs_visibility_timeout` | 6× Lambda timeout (recomendação AWS) |
| SQS maxReceiveCount | 3 | `sqs_max_receive_count` | Tentativas antes de DLQ |
| SQS retenção principal | 4 dias | `sqs_retention_days` | Default AWS |
| DLQ retenção | 14 dias | `dlq_retention_days` | Tempo para investigar |
| TTL DynamoDB Sessions | 24h | `session_ttl_hours` | Limpeza automática |
| TTL DynamoDB Idempotency | 24h | `idempotency_ttl_hours` | Limpeza automática |
| Batch size | 5 | `integrator_batch_size` | Conservador para POC |
| Lambda memory | 256 MB | `lambda_memory_mb` | Todas as Lambdas |

**Invariante:** `SQS VisibilityTimeout (360s) >> Lease (90s) > Lambda timeout (60s)`

---

## O. Checklists Mestre

### Antes do Terraform

| Item | Responsável | Evidência | Status |
|------|-------------|-----------|--------|
| Conta AWS confirmada | Operador | `aws sts get-caller-identity` | [ ] |
| Região escolhida | Equipe | Documentado | [ ] |
| Instância Connect criada | Operador | `aws connect list-instances` | [ ] |
| Instance ID e ARN copiados | Operador | terraform.tfvars preenchido | [ ] |
| Python 3.12+ instalado | Operador | `python --version` | [ ] |
| Terraform instalado | Operador | `terraform -version` | [ ] |
| Testes passando | Operador | `python -m pytest` → 241 passed | [ ] |
| ZIPs gerados | Operador | `.\scripts\build_lambdas.ps1` OK | [ ] |
| terraform.tfvars preenchido | Operador | Variáveis obrigatórias presentes | [ ] |
| terraform init | Operador | Sem erros | [ ] |
| terraform validate | Operador | "Success!" | [ ] |
| terraform plan | Operador | Plan revisado | [ ] |

### Depois do Terraform e antes do teste

| Item | Responsável | Evidência | Status |
|------|-------------|-----------|--------|
| `terraform apply` executado | Operador | "Apply complete!" | [ ] |
| Outputs verificados | Operador | `terraform output` | [ ] |
| Lambda autorizada no Connect | Operador | ARN aparece no console Connect | [ ] |
| Contact Flow criado | Operador | Flow publicado | [ ] |
| Bloco Lambda com timeout 8s | Operador | Configuração visível no editor | [ ] |
| Hosted Chat Widget criado | Operador | Widget funcional | [ ] |
| Domínio localhost:8080 permitido | Operador | Configuração do widget | [ ] |
| E-mail de alarme confirmado | Operador | Subscription confirmed (se aplicável) | [ ] |

### Depois do teste e antes de encerrar a POC

| Item | Responsável | Evidência | Status |
|------|-------------|-----------|--------|
| Testes 1-6 executados | Equipe | Resultados documentados | [ ] |
| Logs verificados (sem erros inesperados) | Equipe | CloudWatch consultado | [ ] |
| DLQ vazia | Equipe | `aws sqs get-queue-attributes` | [ ] |
| Alarmes OK | Equipe | Console CloudWatch → Alarms | [ ] |
| Evidências salvas | Equipe | Screenshots, exports | [ ] |
| Decisão: manter ou destruir | Responsável | Documentada | [ ] |
| terraform destroy (se decidido) | Operador | "Destroy complete!" | [ ] |
| Instância Connect removida (se decidido) | Operador | `aws connect delete-instance` | [ ] |

---

## P. Registro de Implantação

```
Data:                    ____/____/________
Conta AWS:               ____________
Região:                  ____________
Perfil AWS:              ____________
Commit Git:              ____________
Terraform version:       ____________
AWS provider version:    ____________
Connect Instance ID:     ____________
Plan salvo em:           terraform/tfplan
Responsável aprovação:   ____________
Resultado do apply:      [ ] Sucesso  [ ] Falha
Teste realizado:         [ ] Sim  [ ] Não
Incidentes:              ____________
Data prevista destruição:____/____/________
```

---

## Referências

- [ARCHITECTURE.md](../ARCHITECTURE.md) — Decisões técnicas detalhadas
- [terraform/](../terraform/) — Todos os arquivos .tf
- [scripts/build_lambdas.ps1](../scripts/build_lambdas.ps1) — Build das Lambdas
- [.env.example](../.env.example) — Variáveis de ambiente locais
- [terraform.tfvars.example](../terraform/terraform.tfvars.example) — Template de variáveis Terraform
