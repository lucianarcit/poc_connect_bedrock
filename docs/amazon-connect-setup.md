# Configuração do Amazon Connect — POC Mínima e Atendimento Humano Opcional

> **Contexto:** Esta POC é inicialmente **chat-only, bot-only**, sem voz e sem agente humano.
> Não se trata de um call center tradicional. Não há IVR, URA, telefone ou canal de voz.
>
> **Terminologia:**
> - **Contact Flow de Chat** (não IVR — IVR é um termo associado a canais de voz)
> - **Amazon Connect Communications Widget** (widget de comunicação hospedado)
> - **Handoff para agente humano** (transferência do bot para um atendente)

---

## 1. Classificação das Configurações

| Configuração | POC atual (bot-only) | Handoff humano | Não utilizado |
|-------------|---------------------|----------------|---------------|
| Instância Amazon Connect | ✅ Obrigatório | ✅ Obrigatório | — |
| Usuário administrador | ✅ Obrigatório | ✅ Obrigatório | — |
| Security profile Admin | ✅ Obrigatório | ✅ Obrigatório | — |
| Idioma/locale pt-BR | ✅ Obrigatório | ✅ Obrigatório | — |
| Lambda Initializer autorizada | ✅ Obrigatório | ✅ Obrigatório | — |
| Contact Flow de Chat | ✅ Obrigatório | ✅ Obrigatório | — |
| Communications Widget | ✅ Obrigatório | ✅ Obrigatório | — |
| Domínio permitido no widget | ✅ Obrigatório | ✅ Obrigatório | — |
| Flow logs habilitados | ✅ Obrigatório | ✅ Obrigatório | — |
| Monitoramento (CloudWatch) | ✅ Obrigatório | ✅ Obrigatório | — |
| Horário de operação | — | ✅ Obrigatório | — |
| Filas (queues) de chat | — | ✅ Obrigatório | — |
| Routing profiles | — | ✅ Obrigatório | — |
| Usuário agente | — | ✅ Obrigatório | — |
| Security profile de agente | — | ✅ Obrigatório | — |
| Transfer to queue no flow | — | ✅ Obrigatório | — |
| Número de telefone | — | — | ❌ Não utilizado |
| Telefonia (inbound/outbound) | — | — | ❌ Não utilizado |
| IVR / URA de voz | — | — | ❌ Não utilizado |
| Caller ID | — | — | ❌ Não utilizado |
| Outbound calling | — | — | ❌ Não utilizado |
| Gravação / transcrição de voz | — | — | ❌ Não utilizado |

---

## 2. Trilha A — POC Mínima (Bot-Only)

### 2.1 Criar Instância Amazon Connect

- **Console:** AWS Console → Amazon Connect → "Add an instance"
- **Menu:** `https://console.aws.amazon.com/connect/`
- **Passos:**
  1. Identity management: "Store users within Amazon Connect"
  2. Instance alias: `mcp-poc-dev` (ou nome da sua escolha)
  3. Administrator: criar usuário admin (username + password)
  4. Telephony: **desmarcar** "I want to make outbound calls" e "I want to receive inbound calls" (não usamos voz)
  5. Data storage: aceitar padrões
  6. Review and Create
- **Região:** Deve ser **a mesma** configurada em `terraform.tfvars` (`aws_region`). Não é possível alterar depois.
- **Valores a guardar:**
  - Instance ID: visível na URL do console (`/instance/<ID>`)
  - Instance ARN: `arn:aws:connect:<region>:<account>:instance/<ID>`
  - Instance alias: ex. `mcp-poc-dev`
  - Região: ex. `us-east-1`
- **Validação:**
  ```powershell
  aws connect list-instances --region us-east-1 --query "InstanceSummaryList[].{Id:Id,Arn:Arn,Alias:InstanceAlias}" --output table
  ```
- **Erro comum:** Criar em região diferente da do Terraform. Não há como migrar.

### 2.2 Verificar Acesso Administrativo

- **Console:** AWS Console → Amazon Connect → selecionar instância → "Account overview"
- **Validação:** Login no admin website (`https://<alias>.my.connect.aws`) funciona com o usuário criado.
- **Erro comum:** Esquecer a senha do administrador criado na etapa anterior.

### 2.3 Configurar Idioma pt-BR

O idioma afeta a interface do Communications Widget e os prompts do sistema.

- **No Contact Flow** (etapa 2.9): adicionar bloco "Set contact attributes"
  - Tipo: User-defined
  - Key: `customerLocale`
  - Value: `pt-BR`
- **No Communications Widget** (etapa 2.11): configurar textos personalizados em português
- **Validação:** Mensagens do widget aparecem em português.
- **Erro comum:** Usar `pt_BR` em vez de `pt-BR`.

### 2.4 Preencher terraform.tfvars

Após criar a instância:

```powershell
cd C:\proj\poc_connect\terraform
Copy-Item terraform.tfvars.example terraform.tfvars
```

Preencher:
```hcl
connect_instance_id  = "<ID obtido na etapa 2.1>"
connect_instance_arn = "<ARN obtido na etapa 2.1>"
aws_region           = "<mesma região da instância>"
```

### 2.5 Gerar Pacotes Lambda e Executar Terraform

```powershell
cd C:\proj\poc_connect
.\scripts\build_lambdas.ps1

cd terraform
terraform fmt -recursive
terraform init
terraform validate
terraform plan -out=tfplan
```

> ⚠️ Não execute `terraform apply` sem revisão e aprovação.

### 2.6 Aplicar Terraform (após aprovação)

```powershell
terraform apply tfplan
```

Consultar outputs:
```powershell
terraform output initializer_lambda_arn
terraform output sns_topic_arn
```

### 2.7 Autorizar Lambda Initializer na Instância

> ⚠️ Esta operação é feita no **console AWS**, não no admin website da instância.

- **Console:** AWS Console → Amazon Connect → selecionar instância → menu "Flows" → seção "AWS Lambda"
- **Passos:**
  1. Colar o ARN do output `initializer_lambda_arn`
  2. Clicar "Add Lambda Function"
- **Valor:** `arn:aws:lambda:<region>:<account>:function:connect-mcp-poc-dev-initializer`
- **Validação:** ARN aparece na lista.
- **Erro comum:** Lambda em região diferente da instância; colar ARN com `:$LATEST`.

### 2.8 Habilitar Flow Logs

- **Console:** AWS Console → Amazon Connect → selecionar instância → menu "Flows"
- **Passos:**
  1. Seção "Contact flow logs" → habilitar
  2. Ou: dentro do admin website, no editor do Contact Flow, ativar logging
- **Log Group:** `/aws/connect/<instance-alias>`
- **Como consultar:**
  ```powershell
  aws logs filter-log-events --log-group-name "/aws/connect/mcp-poc-dev" --filter-pattern "ContactId" --region us-east-1
  ```
- **Correlação:** Usar o Contact ID presente nos logs das Lambdas e nos flow logs para rastrear o mesmo chat.
- **O que NÃO aparece nos flow logs:** conteúdo das mensagens, tokens, dados descriptografados.
- **Distinguir erros:**
  - Erro no flow → flow logs (ex: Lambda timeout, condition mismatch)
  - Erro na Initializer → CloudWatch `/aws/lambda/...-initializer`
  - Erro no Integrator → CloudWatch `/aws/lambda/...-integrator`

### 2.9 Criar Contact Flow de Chat

> Esta etapa é feita no **admin website** da instância (`https://<alias>.my.connect.aws`).

- **Menu:** Routing → Contact flows → "Create contact flow"
- **Passos:**
  1. Nome: `MCP-POC-Chat-Flow`
  2. Tipo: Contact flow (não Customer queue flow)
  3. **Bloco "Set contact attributes"** (opcional mas recomendado):
     - Tipo: User-defined
     - Key: `customerLocale` / Value: `pt-BR`
  4. **Bloco "Invoke AWS Lambda Function"**:
     - Selecionar: `connect-mcp-poc-dev-initializer`
     - Timeout: `8` segundos
     - Este timeout é o limite síncrono para a resposta da Lambda ao Contact Flow
  5. Ramificação **Success**:
     - O bot foi inicializado. O contato precisa permanecer ativo para que as mensagens trafeguem pelo streaming.
     - **Nota:** O desenho de manutenção da sessão é específico da POC e deve ser validado no teste de chat real. Possibilidades: bloco Wait com timeout, Loop, ou Transfer.
  6. Ramificação **Error**:
     - Bloco "Disconnect" (o bot não conseguiu inicializar)
  7. **Publicar** (botão "Publish")
- **Valor a guardar:** Contact Flow ID (extraído da URL: `contact-flow/<ID>`)
- **Validação:** Status = "Published" na lista de flows.
- **Erro comum:** Flow em "Draft" (nunca publicado); Lambda não autorizada; timeout menor que 8s.

### 2.10 Verificar Resposta da Lambda no Flow

O handler da Initializer (`src/initializer/handler.py`) retorna:

```json
{"status": "SUCCESS", "botInitialized": "true"}
```

ou em caso de erro:

```json
{"status": "ERROR", "botInitialized": "false", "errorCode": "..."}
```

O Contact Flow pode usar "Check contact attributes" → External → `status` = `SUCCESS` para ramificar.

### 2.11 Criar Amazon Connect Communications Widget

> Esta etapa é feita no **admin website** da instância.

- **Menu:** Channels → Chat → "Add communications widget" (ou "Customize widget")
- **Passos:**
  1. Selecionar o Contact Flow: `MCP-POC-Chat-Flow`
  2. **Textos em português:**
     - Título: `Assistente Virtual`
     - Subtitle/descrição: `Tire suas dúvidas sobre nossos serviços`
     - Placeholder: `Digite sua mensagem...`
     - Botão: `Iniciar chat`
  3. Domínios permitidos: `http://localhost:8080`
  4. Copiar o snippet `<script>` gerado
- **Validação:** Widget renderiza no browser ao acessar `http://localhost:8080`.
- **Erro comum:** Usar `https://localhost` (precisa ser `http://`); não adicionar a porta; abrir via `file://` (bloqueado).

### 2.12 Incorporar Widget em Página HTML de Teste

Criar arquivo `test.html` (ou qualquer nome) na raiz do projeto ou em diretório de teste:

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><title>POC Chat Test</title></head>
<body>
  <h1>Teste do Chat — POC MCP</h1>
  <p>O widget deve aparecer no canto inferior direito.</p>
  <!-- COLAR O SNIPPET DO WIDGET AQUI -->
</body>
</html>
```

Servir localmente:
```powershell
python -m http.server 8080
```

Acessar: `http://localhost:8080/test.html`

### 2.13 Testar Ponta a Ponta

1. Abrir `http://localhost:8080/test.html`
2. Clicar no widget para iniciar chat
3. Enviar: `qual o status do sistema`
4. Aguardar resposta do bot ("Status: healthy | Documentos: ...")
5. Enviar: `como redefinir minha senha`
6. Aguardar resposta com conteúdo do DOC-001
7. Enviar mensagem com acentos: `não consigo acessar o serviço`
8. Verificar que acentos são processados corretamente

### 2.14 Validar Observabilidade

Após o teste:

```powershell
# Flow logs
aws logs filter-log-events --log-group-name "/aws/connect/mcp-poc-dev" --region us-east-1 --limit 5

# Initializer
aws logs tail "/aws/lambda/connect-mcp-poc-dev-initializer" --since 10m --region us-east-1

# Integrator
aws logs tail "/aws/lambda/connect-mcp-poc-dev-integrator" --since 10m --region us-east-1

# MCP Server
aws logs tail "/aws/lambda/connect-mcp-poc-dev-mcp-server" --since 10m --region us-east-1

# DynamoDB Sessions (verificar registro criado)
aws dynamodb scan --table-name connect-mcp-poc-dev-sessions --region us-east-1 --max-items 3

# SQS DLQ (deve estar vazia)
aws sqs get-queue-attributes --queue-url <DLQ_URL> --attribute-names ApproximateNumberOfMessages --region us-east-1
```

### 2.15 Recursos Padrão da Instância

Ao criar uma instância Amazon Connect, ela pode conter recursos pré-criados:

| Recurso padrão | Uso na POC |
|----------------|-----------|
| BasicQueue | Não usar — sem agentes na POC mínima |
| Basic Routing Profile | Não usar — sem agentes na POC mínima |
| Default contact flows | Não usar — criar flow específico `MCP-POC-Chat-Flow` |

> **Nota:** Recursos padrão podem ajudar em testes rápidos de conectividade, mas não devem ser utilizados sem verificar se a configuração é compatível com o fluxo da POC. Para handoff humano (Trilha B), preferir criar recursos com nomes explícitos.

---

## 3. Número de Telefone — Não Necessário

> ❌ **Esta POC não requer claim de número de telefone.**

- O canal é **chat via Communications Widget** (browser/HTTPS)
- Não há entrada de voz, IVR, URA ou callbacks telefônicos
- Não é necessário configurar telefonia, caller ID ou outbound calling
- Se futuramente adicionarmos canal de voz, número será necessário nesse momento

**Remova "número de telefone" de qualquer checklist obrigatório da POC.**

---

## 4. Trilha B — Handoff Humano (Opcional)

> ⚠️ **Opcional — necessário somente se o bot transferir o chat a um agente humano.**
> A POC mínima funciona completa sem esta seção.

### 4.1 Criar Horário de Operação

- **Admin website:** Routing → Hours of operation → "Add new hours"
- **Configuração:**
  - Nome: `POC-Chat-Hours`
  - Timezone: `America/Sao_Paulo` (ou conforme necessidade)
  - Dias e horas: ex. Segunda a Sexta, 08:00–18:00
  - Feriados/overrides: configurar se necessário para evitar transferência em datas sem agentes
- **Validação:** Horário aparece na lista.
- **Conceito:** Horários de operação definem quando os agentes estão disponíveis. Fora do horário, o flow pode enviar mensagem automática e não transferir.

### 4.2 Criar Fila de Chat

- **Admin website:** Routing → Queues → "Add new queue"
- **Configuração:**
  - Nome: `POC-MCP-Chat-Queue`
  - Hours of operation: `POC-Chat-Hours`
  - Description: `Fila de atendimento humano para a POC MCP`
  - Canais: habilitar **Chat**
  - Comportamento fora do horário: definido pelo flow (não pela fila em si)
- **Validação:** Fila aparece na lista.
- **Conceito:** Queues são "salas de espera". Mensagens ficam na fila até um agente estar disponível. Não confundir com SQS — são conceitos diferentes.

### 4.3 Criar Security Profile de Agente

- **Admin website:** Users → Security profiles → "Add new security profile"
- **Configuração:**
  - Nome: `POC-Chat-Agent-Profile`
  - **Permissões mínimas:**
    - Contact Control Panel (CCP): acesso
    - Chat: habilitar
    - Contact handling: permitir aceitar/rejeitar contatos
  - **Não conceder:** Admin, números de telefone, routing config, user management
- **Validação:** Profile aparece na lista.
- **Erro comum:** Conceder perfil Admin ao agente (expõe configurações da instância).

### 4.4 Criar Routing Profile

- **Admin website:** Users → Routing profiles → "Add new profile"
- **Configuração:**
  - Nome: `POC-MCP-Chat-Routing`
  - **Canal Chat:** habilitado
  - **Fila associada:** `POC-MCP-Chat-Queue` com prioridade 1, delay 0
  - **Simultaneidade de chat:** 2–5 (quantos chats o agente atende ao mesmo tempo)
- **Validação:** Profile aparece e mostra a fila associada.
- **Conceito:** Routing profiles ligam agentes a filas. Sem routing profile com a fila correta, o agente nunca recebe chats daquela fila.

### 4.5 Criar Usuário Agente

- **Admin website:** Users → User management → "Add new users"
- **Configuração:**
  - Username e senha
  - Security profile: `POC-Chat-Agent-Profile`
  - Routing profile: `POC-MCP-Chat-Routing`
  - Phone type: **None** (cenário chat-only — sem soft phone)
  - Hierarquia: opcional
- **Validação:** Usuário consegue fazer login no CCP/Agent Workspace.
- **Erro comum:** Atribuir routing profile que não inclui canal Chat.

### 4.6 Alterar Contact Flow para Transfer

Editar `MCP-POC-Chat-Flow` para adicionar caminho de transferência:

1. Após o bot inicializar (Success), adicionar lógica de decisão:
   - Se o bot detectar intenção de falar com humano (ex: via atributo ou palavra-chave)
   - **Bloco "Set working queue"**: selecionar `POC-MCP-Chat-Queue`
   - **Bloco "Check hours of operation"**: verificar se está no horário
     - In hours → **"Transfer to queue"**
     - Out of hours → enviar mensagem "Fora do horário" → Disconnect ou manter bot
   - **Bloco "Check staffing"** (opcional): verifica se há agentes disponíveis
2. **Publicar** a versão atualizada

> **Nota:** O mecanismo de detecção do handoff (como o bot decide transferir) é implementado no código do Integrator. Na POC atual, o `tool_selector` identifica keywords como "falar com atendente", "humano", "transferir".

### 4.7 Testar Handoff

| Cenário | Procedimento | Resultado esperado |
|---------|-------------|-------------------|
| Agente online, dentro do horário | Enviar "falar com atendente" | Chat transfere para fila, agente recebe no CCP |
| Agente offline | Enviar "falar com atendente" | Mensagem indica indisponibilidade ou chat fica em espera |
| Dentro do horário, fila vazia | Nenhum agente logado | Chat aguarda na fila até timeout |
| Fora do horário | Enviar "falar com atendente" | Flow detecta e informa "fora do horário" |
| Bot resolve sem transferência | Perguntar sobre documentação | Resposta direta, sem entrar na fila |
| Timeout na fila | Agente não aceita | Comportamento definido no flow (disconnect ou volta ao bot) |
| Cliente encerra durante espera | Fechar widget | Contato finalizado |

---

## 5. Idioma pt-BR — Detalhes

### No Contact Flow
- Bloco "Set contact attributes" com `customerLocale = pt-BR`
- Todos os prompts/mensagens em português

### No Communications Widget
- Título, subtítulo, placeholder e botão personalizados em português
- Sem fallback automático para inglês (configurar todos os textos)

### No Código
- `sample_documents/` contém documentos em português
- `tool_selector.py` normaliza Unicode (remove acentos) para matching de keywords
- Respostas do MCP são em português

### Teste de Acentos e Unicode
- Enviar mensagem com: `não`, `ação`, `resolução`, `serviço`
- Verificar que o bot responde corretamente (sem erro de encoding)
- Validar nos logs que o content_type é `text/plain` com caracteres preservados

---

## 6. Flow Logs — Habilitar e Validar

### Habilitar
- **Console AWS:** Amazon Connect → instância → Flows → "Enable contact flow logs"
- **Alternativa:** No editor do flow, adicionar bloco "Set logging behavior" = Enable

### Consultar
- **Log Group:** `/aws/connect/<instance-alias>`
- **Conteúdo:** Eventos de execução do flow (blocos executados, decisões, erros)

### Correlação com Contact ID
Todos os componentes registram o Contact ID:
- Flow logs: campo `ContactId`
- Lambda Initializer: `extra={"contact_id": ...}`
- Lambda Integrator: `extra={"contact_id": ...}`
- DynamoDB: `pk = CONTACT#<contact_id>`

### O que NÃO aparece nos flow logs
- Conteúdo das mensagens do chat
- Tokens (ParticipantToken, ConnectionToken)
- Dados descriptografados
- Valores de atributos sensíveis

### Distinguir origem do erro
| Onde olhar | Tipo de erro |
|-----------|-------------|
| Flow logs (`/aws/connect/...`) | Timeout de Lambda, bloco não encontrado, condição inválida |
| Lambda Initializer (`/aws/lambda/...-initializer`) | APIs Connect falharam, DynamoDB error, KMS error |
| Lambda Integrator (`/aws/lambda/...-integrator`) | Parsing SQS, idempotência, MCP, SendMessage |

---

## 7. Troubleshooting — Amazon Connect

| Sintoma | Causa provável | Correção |
|---------|---------------|----------|
| Agente não recebe o chat | Fila ausente no routing profile | Associar `POC-MCP-Chat-Queue` e canal Chat ao routing profile |
| Agente não aparece disponível | Status offline ou canal Chat desabilitado | Alterar status para "Available" no CCP e verificar routing profile |
| Chat fica preso na fila | Nenhum agente elegível | Verificar staffing, routing profile e limite de simultaneidade |
| Transfer to queue falha | Working queue não definida | Adicionar bloco "Set working queue" antes do Transfer |
| Atendimento ocorre fora do horário | Flow não verifica horário | Adicionar bloco "Check hours of operation" |
| Usuário não acessa CCP | Security profile insuficiente | Ajustar `POC-Chat-Agent-Profile` com permissões mínimas |
| Widget funciona sem telefone | Comportamento esperado | Chat não exige número telefônico |
| Flow de voz confundido com chat | Tipo de flow incorreto | Criar "Contact flow" (não "Customer whisper" ou "Agent whisper") |
| Widget não carrega | Domínio de origem não permitido | Adicionar `http://localhost:8080` nos domínios do widget |
| Widget abre mas chat não conecta | Contact Flow não publicado | Publicar flow (status "Published") |
| Lambda timeout no flow | Timeout do bloco < 8s ou Lambda lenta | Configurar timeout 8s no bloco; verificar Initializer logs |
| Mensagens com acentos cortadas | Encoding incorreto | Verificar que content_type=text/plain UTF-8; testar com `ã`, `ç`, `ó` |
| Flow log não aparece | Logging não habilitado | Habilitar em Flows → Contact flow logs |
| "Lambda function not found" | Lambda não autorizada | Console → Flows → AWS Lambda → adicionar ARN |

---

## Referências

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) — Manual completo de implantação Terraform + AWS
- [ARCHITECTURE.md](../ARCHITECTURE.md) — Decisões técnicas, diagramas, modelos DynamoDB
- [Documentação Amazon Connect](https://docs.aws.amazon.com/connect/)
- [Communications Widget Setup](https://docs.aws.amazon.com/connect/latest/adminguide/add-chat-to-website.html)
