# Recursos Manuais — Resumo

> Recursos que **NÃO** são criados pelo Terraform e precisam de configuração manual.

| Recurso Manual | Quando Criar | Onde Criar | Dados a Guardar | Como Validar |
|---------------|-------------|-----------|-----------------|-------------|
| Instância Amazon Connect | Antes do Terraform | Console AWS → Amazon Connect → Add instance | Instance ID, Instance ARN, Região | `aws connect list-instances` |
| Autorização Lambda no Connect | Após `terraform apply` | Console Connect → Contact flows → AWS Lambda | — | ARN aparece na lista |
| Contact Flow de Chat | Após autorizar Lambda | Console Connect → Routing → Contact flows | Contact Flow ID | Flow em status "Published" |
| Bloco Invoke Lambda (no flow) | Ao criar Contact Flow | Editor do Contact Flow → Add block | — | Lambda selecionada, timeout 8s |
| Hosted Chat Widget | Após publicar Contact Flow | Console Connect → Channels → Chat → Widget | Snippet JS | Widget carrega no browser |
| Domínio permitido no Widget | Ao criar Widget | Configuração do Widget | — | Widget não mostra erro de origem |
| Confirmação e-mail alarme | Após apply (se alarm_email preenchido) | E-mail do destinatário | — | Subscription status = Confirmed |
| Página HTML de teste | Para testar o widget | Arquivo local servido via `python -m http.server 8080` | — | Widget abre e conecta |

## Dados que o Terraform precisa ANTES do apply

| Dado | De onde vem | Variável Terraform |
|------|------------|-------------------|
| Instance ID | Console Connect ou CLI | `connect_instance_id` |
| Instance ARN | Console Connect ou CLI | `connect_instance_arn` |
| Região AWS | Escolha ao criar instância | `aws_region` |

## Dados que saem do Terraform PARA configuração manual

| Output Terraform | Onde usar |
|-----------------|----------|
| `initializer_lambda_arn` | Autorização Lambda no Connect + bloco do Contact Flow |
| `sns_topic_arn` | Código da Initializer usa automaticamente (env var) |
| `mcp_server_function_url` | Código do Integrator usa automaticamente (env var) |
