# Deployment — Terraform

## Pré-requisitos

- Terraform >= 1.6
- AWS CLI configurado com credenciais (profile ou env vars)
- Python 3.12+ com pip (para build dos ZIPs)
- Instância Amazon Connect já criada
- PowerShell (Windows) para o script de build

## Estrutura

```
terraform/
├── data.tf              # Data sources (caller_identity, region)
├── dynamodb.tf          # Tabelas Sessions e Idempotency
├── event_source.tf      # SQS → Lambda Integrator mapping
├── function_url.tf      # Lambda Function URL (MCP Server, AWS_IAM)
├── iam.tf               # Roles e policies para as 3 Lambdas
├── kms.tf               # CMK para criptografia de tokens
├── lambda.tf            # Lambda functions (Initializer, Integrator, MCP Server)
├── locals.tf            # Nomes, prefixos, timings calculados
├── monitoring.tf        # Log groups, metric filters, alarmes
├── outputs.tf           # ARNs, URLs, nomes para referência
├── providers.tf         # Provider AWS com default_tags
├── sns.tf               # SNS Topic para streaming
├── sqs.tf               # SQS principal + DLQ + policy SNS→SQS
├── terraform.tfvars.example  # Template de variáveis (nunca commitar .tfvars real)
├── variables.tf         # Todas as variáveis de entrada
└── versions.tf          # Terraform e provider versions
```

## 1. Build dos Lambdas

```powershell
.\scripts\build_lambdas.ps1
```

Verifica:
- Os ZIPs são criados em `packages/` (initializer.zip, integrator.zip, mcp_server.zip)
- Dependências Linux (manylinux2014_x86_64, cp312)
- boto3 excluído (Lambda runtime fornece)
- Separadores POSIX nos nomes internos

## 2. Configuração

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars com valores reais
```

Variáveis obrigatórias:
- `connect_instance_id` — ID da instância Amazon Connect
- `connect_instance_arn` — ARN da instância Amazon Connect

## 3. Init

```bash
terraform init
```

Baixa providers e inicializa backend. O arquivo `.terraform.lock.hcl` é versionado.

## 4. Plan

```bash
terraform plan -out=tfplan
```

Revise os recursos que serão criados:
- 3 Lambda Functions
- 1 Lambda Function URL (AWS_IAM)
- 3 IAM Roles + policies
- 2 DynamoDB Tables
- 1 KMS Key + alias
- 1 SNS Topic + subscription
- 2 SQS Queues (principal + DLQ)
- 1 Event Source Mapping (SQS → Integrator)
- 3 CloudWatch Log Groups
- 1 Metric Filter
- 6 CloudWatch Alarms
- 1 SNS Topic para alarmes (se alarm_email configurado)

## 5. Apply

```bash
terraform apply tfplan
```

Após o apply, os outputs mostram:
- `sns_topic_arn` — configurar no Contact Flow (StartContactStreaming)
- `mcp_server_function_url` — URL HTTPS do MCP Server
- `initializer_lambda_arn` — configurar no Contact Flow (Invoke Lambda)

## 6. Verificação pós-deploy

```bash
# Verificar Function URL
aws lambda get-function-url-config --function-name connect-mcp-poc-dev-mcp-server

# Verificar event source mapping
aws lambda list-event-source-mappings --function-name connect-mcp-poc-dev-integrator

# Enviar mensagem de teste (requer Contact Flow configurado)
```

## 7. Destroy

```bash
terraform destroy
```

Remove todos os recursos. A KMS key entra em período de waiting (7 dias) antes da exclusão definitiva.

**Atenção**: DynamoDB tables com dados serão excluídas permanentemente. Para produção, considere `prevent_destroy`.

## Timings configurados

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| Lambda Initializer timeout | 8s | Contact Flow sync timeout |
| Lambda Integrator timeout | 60s | Processamento MCP + SendMessage |
| Lambda MCP Server timeout | 30s | POC: tools rápidas |
| Lease de idempotência | 90s | > Lambda timeout para evitar conflito |
| SQS VisibilityTimeout | 360s | 6x Lambda Integrator (recomendação AWS) |
| SQS maxReceiveCount | 3 | 3 tentativas antes de DLQ |
| SQS retenção principal | 4 dias | Default AWS |
| DLQ retenção | 14 dias | Tempo para investigar |
| TTL DynamoDB | 24h | Limpeza automática |
| Batch size | 5 | Conservador para POC |

## Resource = "*" justificativas

| Action | Motivo |
|--------|--------|
| `connect:StartContactStreaming` | API não suporta resource-level permissions |
| `connect:CreateParticipant` | API não suporta resource-level permissions |

## Nota sobre connectparticipant

As APIs `connectparticipant:*` (SendMessage, CreateParticipantConnection) **não usam IAM/SigV4**.
São autenticadas por ConnectionToken/ParticipantToken emitidos pelo Connect.
Não há actions IAM necessárias para essas chamadas.
