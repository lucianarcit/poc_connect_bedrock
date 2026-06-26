# Recursos Manuais — Resumo

> Recursos que **NÃO** são criados pelo Terraform e precisam de configuração manual.
> Detalhes completos em [amazon-connect-setup.md](amazon-connect-setup.md).

## POC Mínima (Bot-Only)

| Recurso Manual | Quando Criar | Onde Criar | Dados a Guardar | Como Validar |
|---------------|-------------|-----------|-----------------|-------------|
| Instância Amazon Connect | Antes do Terraform | Console AWS → Amazon Connect | Instance ID, ARN, Região, Alias | `aws connect list-instances` |
| Usuário administrador | Ao criar instância | Wizard de criação | Username, senha | Login no admin website |
| Autorização Lambda | Após apply (✅ concluído) | Console AWS → Connect → instância → Flows → AWS Lambda | — | ARN na lista |
| Flow logs | Após criar instância | Console AWS → Connect → instância → Flows | — | Log group existe |
| Contact Flow de Chat | Após autorizar Lambda (apply ✅) | Admin website → Routing → Contact flows | Contact Flow ID | Status "Published" |
| Communications Widget | Após publicar flow (apply ✅) | Admin website → Channels → Chat | Snippet JS | Widget renderiza |
| Domínio permitido | Ao criar widget | Config do widget | — | Widget carrega |
| Página HTML de teste | Para testar | Arquivo local + `python -m http.server 8080` | — | localhost:8080 funciona |
| Confirmação e-mail alarme | Após apply (se alarm_email) | E-mail do destinatário | — | Subscription confirmed |

## Handoff Humano (Opcional)

| Recurso Manual | Quando Criar | Onde Criar | Dados a Guardar | Como Validar |
|---------------|-------------|-----------|-----------------|-------------|
| Horário de operação | Antes de configurar fila | Admin website → Routing → Hours | Nome, timezone | Listado em Hours |
| Fila de chat | Após horário | Admin website → Routing → Queues | Nome | Canal Chat habilitado |
| Security profile agente | Antes do usuário | Admin website → Users → Security profiles | Nome | Permissões corretas |
| Routing profile | Após fila | Admin website → Users → Routing profiles | Nome | Fila associada |
| Usuário agente | Após routing profile | Admin website → Users → User management | Username | Login CCP funciona |
| Alteração do Contact Flow | Após filas | Admin website → editor do flow | — | Flow republicado |

## Não Necessário

| Recurso | Motivo |
|---------|--------|
| Número de telefone | POC chat-only via widget |
| Telefonia | Sem canal de voz |
| IVR / URA | Conceito de voz |
| Caller ID | Sem chamadas |
| Gravação de voz | Sem voz |

## Dados: Terraform ← → Manual

| Dado | Direção | Variável/Output |
|------|---------|-----------------|
| Instance ID | Manual → Terraform | `connect_instance_id` |
| Instance ARN | Manual → Terraform | `connect_instance_arn` |
| Região | Manual → Terraform | `aws_region` |
| Lambda Initializer ARN | Terraform → Manual | `initializer_lambda_arn` (autorizar no Connect — **Lambda já criada**) |
| SNS Topic ARN | Terraform → Código | `sns_topic_arn` (env var automática; topic policy Connect→SNS criada pelo Terraform) |
| MCP Server URL | Terraform → Código | `mcp_server_function_url` (env var automática) |

## Cadeia de permissões (todas criadas pelo Terraform)

```
Connect ─[sns:Publish]─► SNS Topic    (aws_sns_topic_policy.allow_connect em sns.tf)
SNS     ─[sqs:SendMessage]─► SQS     (aws_sqs_queue_policy.allow_sns em sqs.tf)
SQS     ─[event source]─► Integrator  (aws_lambda_event_source_mapping em event_source.tf)
Integrator ─[SigV4]─► Function URL   (IAM + aws_lambda_function_url em iam.tf + function_url.tf)
```
