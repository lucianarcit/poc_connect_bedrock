# Troubleshooting — Matriz de Problemas e Soluções

## Terraform e Deploy

| Sintoma | Causa provável | Onde olhar | Correção |
|---------|---------------|-----------|----------|
| `var.connect_instance_id` pedido interativamente | `terraform.tfvars` ausente ou incompleto | `terraform/terraform.tfvars` | Copiar de `terraform.tfvars.example` e preencher |
| `Error: Invalid ARN` no plan | Formato ARN incorreto | `terraform.tfvars` → `connect_instance_arn` | Formato: `arn:aws:connect:REGIAO:CONTA:instance/ID` |
| `filebase64sha256: no file exists` | ZIPs não gerados | `packages/` | Executar `.\scripts\build_lambdas.ps1` |
| `Error: Unsupported Terraform Core version` | Terraform desatualizado | Terminal | Instalar Terraform >= 1.6 |
| Plan mostra 0 resources | `terraform init` não executado | `.terraform/` ausente | `terraform init` |
| `iam:CreateRole` com explicit deny | Role sem sufixo `-PPD` ou sem permissions boundary | `terraform/iam.tf` | Ajustar nome (terminar em `-PPD`), adicionar `permissions_boundary` e tag `Project = "AWS-PPD"`, gerar novo plan |
| Apply parcial (alguns recursos criados, roles falharam) | Governance da conta rejeitou roles | State do Terraform | Corrigir roles e executar novo plan/apply sem destruir recursos existentes |

## Lambda Runtime

| Sintoma | Causa provável | Onde olhar | Correção |
|---------|---------------|-----------|----------|
| `Runtime.ImportModuleError: Unable to import module 'initializer.handler'` | Estrutura do ZIP incorreta | Inspecionar ZIP com Python zipfile | Rebuild; verificar que `initializer/handler.py` está na raiz |
| `ModuleNotFoundError: No module named 'pydantic'` | Dependência ausente no ZIP | ZIP contents | Rebuild; verificar requirements no script |
| `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'` | .so de Windows no ZIP (não Linux) | ZIP → procurar `.pyd` ou `.dll` | Rebuild com `--platform manylinux2014_x86_64` |
| `[Errno 2] No such file: '/var/task/sample_documents'` | `sample_documents/` ausente no ZIP do MCP | ZIP mcp_server.zip | Verificar build script inclui ExtraDirs |

## IAM e Permissões

| Sintoma | Causa provável | Onde olhar | Correção |
|---------|---------------|-----------|----------|
| `AccessDeniedException` no KMS Encrypt | Role Initializer sem kms:Encrypt | CloudWatch → Initializer | Verificar `iam.tf` statement KMSEncrypt |
| `AccessDeniedException` no KMS Decrypt | Role Integrator sem kms:Decrypt | CloudWatch → Integrator | Verificar `iam.tf` statement KMSDecryptEncrypt |
| HTTP 403 na Function URL | Role sem lambda:InvokeFunctionUrl ou assinatura SigV4 inválida | CloudWatch → Integrator | Verificar IAM + MCP_SERVER_URL |
| `An error occurred (AccessDeniedException)` no DynamoDB | Role sem permissão na tabela | CloudWatch | Verificar statements DynamoDB no `iam.tf` |
| `AccessDeniedException` em connect:CreateParticipant | Role sem connect:CreateParticipant | CloudWatch → Initializer | Verificar statement ConnectStreaming |

## Amazon Connect

| Sintoma | Causa provável | Onde olhar | Correção |
|---------|---------------|-----------|----------|
| Contact Flow não invoca Lambda | Lambda não autorizada na instância | Console Connect → Contact flows → AWS Lambda | Adicionar ARN da Lambda |
| Timeout no Contact Flow (>8s) | Initializer lenta ou APIs Connect lentas | CloudWatch → Initializer (duração) | Verificar latência; considerar retry |
| Chat abre mas nenhuma resposta | Streaming não configurado ou Initializer falhou | CloudWatch → Initializer | Verificar log "Initialization complete" |
| Widget não carrega | Domínio de origem não permitido | Console do browser (DevTools → Console) | Adicionar domínio na config do widget |
| `file://` não funciona | Browsers bloqueiam widgets em file:// | — | Servir via `python -m http.server 8080` |
| Widget carrega mas chat não conecta | Contact Flow não publicado ou ARN errado | Console Connect → Contact flows | Publicar flow |

## Processamento de Mensagens

| Sintoma | Causa provável | Onde olhar | Correção |
|---------|---------------|-----------|----------|
| Mensagem no SQS mas não processada | Event source mapping desabilitado | Console Lambda → Configuration → Triggers | Habilitar |
| Mensagem processada duas vezes (resposta duplicada) | Idempotência não funcionando | DynamoDB Idempotency table | Verificar PutItem condicional |
| FAILED_FINAL sem alarme | Metric Filter pattern incorreto | CloudWatch → Metric Filters | Pattern: `{ $.metric = "FailedFinal" }` |
| DLQ com mensagens | 3 falhas consecutivas | CloudWatch → Integrator (erros) | Investigar causa raiz nos logs |
| Token expirado recorrente | Sessões muito longas sem atividade | CloudWatch → "TOKEN_EXPIRED" | Código renova automaticamente; verificar ParticipantToken |
| SigV4 signature mismatch | Clock skew ou body modificado após assinatura | CloudWatch → Integrator | Verificar que `content=body` (não `json=payload`) |
| Bot responde a si mesmo (loop) | Filtro ParticipantRole ausente | CloudWatch → Integrator | event_parser filtra `CUSTOMER` apenas |

## Rede e Conectividade

| Sintoma | Causa provável | Onde olhar | Correção |
|---------|---------------|-----------|----------|
| Lambda sem acesso à internet | Lambda em VPC sem NAT | Configuração Lambda (VPC) | POC não usa VPC; remover config VPC |
| SNS não entrega para SQS | SQS policy ausente | Console SQS → Access Policy | Terraform cria `aws_sqs_queue_policy.allow_sns` |
| Subscription SNS "Pending confirmation" | E-mail de alarme não confirmado | Console SNS → Subscriptions | Clicar link no e-mail |

## Amazon Connect — Handoff Humano

| Sintoma | Causa provável | Onde olhar | Correção |
|---------|---------------|-----------|----------|
| Agente não recebe o chat | Fila ausente no routing profile | Admin website → Routing profiles | Associar fila com canal Chat |
| Agente não aparece disponível | Status offline ou canal Chat desabilitado | CCP → status do agente | Alterar status para "Available"; verificar routing profile |
| Chat fica preso na fila | Nenhum agente elegível | Console Connect → Real-time metrics | Verificar staffing, routing profile e simultaneidade |
| Transfer to queue falha | Working queue não definida no flow | Editor do Contact Flow | Adicionar "Set working queue" antes de Transfer |
| Atendimento ocorre fora do horário | Flow não verifica horário | Editor do Contact Flow | Adicionar "Check hours of operation" |
| Usuário não acessa CCP | Security profile insuficiente | Admin website → Security profiles | Ajustar permissões (CCP access, Chat) |
| Widget funciona sem telefone | Comportamento esperado | — | Chat não exige número telefônico |
| Flow de voz confundido com chat | Tipo de flow incorreto | Admin website → Contact flows | Criar "Contact flow" (não whisper/hold/queue) |

## Amazon Connect — Idioma e Encoding

| Sintoma | Causa provável | Onde olhar | Correção |
|---------|---------------|-----------|----------|
| Widget em inglês | Textos não personalizados | Config do widget | Configurar título/placeholder em pt-BR |
| Acentos corrompidos nos logs | Encoding do log viewer | CloudWatch → formato | Verificar UTF-8; content_type=text/plain funciona |
| Keyword matching falha com acentos | Normalização Unicode ausente | `tool_selector.py` | Código normaliza automaticamente (remover acentos) |
| `customerLocale` ignorado | Atributo não definido no flow | Editor do Contact Flow | Adicionar "Set contact attributes" com `customerLocale=pt-BR` |
