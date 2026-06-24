# Checklist de Implantação — Versão Reduzida

> Versão imprimível. Detalhes completos em [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) e [amazon-connect-setup.md](amazon-connect-setup.md).

---

## POC Mínima (Bot-Only)

### Preparação Local

- [ ] Python 3.12 (runtime de destino) instalado
- [ ] Terraform >= 1.6 instalado
- [ ] AWS CLI v2 instalada
- [ ] `aws sts get-caller-identity` → conta correta
- [ ] `.venv` criado e ativado
- [ ] `pip install -r requirements-dev.txt`
- [ ] `python -m pytest` → todos passando, ≥80% coverage
- [ ] `.\scripts\build_lambdas.ps1` → 3 ZIPs em `packages/`
- [ ] `git check-ignore terraform/tfplan` → confirmado ignorado

### Amazon Connect — Instância

- [ ] Instância criada na **mesma região** do Terraform
- [ ] Instance ID registrado
- [ ] Instance ARN registrado
- [ ] Alias registrado
- [ ] Usuário admin verificado (login no admin website funciona)
- [ ] Idioma/locale pt-BR configurado

### Terraform

- [ ] `terraform.tfvars` preenchido com `connect_instance_id` e `connect_instance_arn`
- [ ] `terraform fmt -recursive`
- [ ] `terraform init`
- [ ] `terraform validate` → "Success!"
- [ ] `terraform plan -out=tfplan` → revisar
- [ ] ⚠️ `terraform apply tfplan` (após aprovação)
- [ ] `terraform output` → guardar ARNs

### Amazon Connect — Pós-Terraform

- [ ] Lambda autorizada: Console AWS → Connect → instância → Flows → AWS Lambda → `initializer_lambda_arn`
- [ ] Flow logs habilitados
- [ ] Contact Flow `MCP-POC-Chat-Flow` criado
- [ ] Bloco "Invoke AWS Lambda" → Initializer, timeout 8s
- [ ] Bloco "Set contact attributes" → `customerLocale = pt-BR`
- [ ] Flow publicado (status "Published")
- [ ] Communications Widget criado → associado ao flow
- [ ] Textos do widget em português
- [ ] Domínio permitido: `http://localhost:8080`
- [ ] Snippet copiado para página HTML de teste

### Teste

- [ ] `python -m http.server 8080`
- [ ] Widget abre e conecta ao chat
- [ ] Enviar "qual o status" → resposta do bot
- [ ] Enviar "como redefinir minha senha" → resposta com conteúdo
- [ ] Enviar mensagem com acentos → resposta correta
- [ ] CloudWatch logs sem erros inesperados
- [ ] DLQ vazia
- [ ] Alarmes em estado OK
- [ ] E-mail de alarme confirmado (se configurado)

### Observabilidade

- [ ] Flow logs consultados (`/aws/connect/<alias>`)
- [ ] Initializer logs consultados
- [ ] Integrator logs consultados
- [ ] DynamoDB Sessions tem registros
- [ ] SNS Topic mostra mensagens publicadas

---

## Handoff Humano (Opcional)

> ⚠️ Necessário somente se o bot transferir o chat a um agente.

- [ ] Horário de operação criado (`POC-Chat-Hours`)
- [ ] Fila criada (`POC-MCP-Chat-Queue`) com canal Chat
- [ ] Security profile de agente criado (`POC-Chat-Agent-Profile`)
- [ ] Routing profile criado (`POC-MCP-Chat-Routing`) com fila e canal Chat
- [ ] Usuário agente criado com routing e security profile corretos
- [ ] Contact Flow editado com Set working queue + Check hours + Transfer to queue
- [ ] Flow republicado
- [ ] Teste: agente online recebe o chat após "falar com atendente"
- [ ] Teste: fora do horário → mensagem adequada
- [ ] Teste: bot resolve sem transferir

---

## Não Utilizado

- [ ] Número de telefone: **NÃO criado** (POC chat-only)
- [ ] Telefonia: **NÃO habilitada**
- [ ] Fluxo de voz/IVR: **NÃO configurado**
- [ ] Caller ID: **NÃO configurado**

---

## Encerramento

- [ ] Evidências de teste salvas
- [ ] Widget removido ou domínio restrito
- [ ] Flow despublicado
- [ ] Autorização Lambda removida
- [ ] `terraform plan -destroy` → revisar
- [ ] ⚠️ `terraform destroy`
- [ ] Opcional: `aws connect delete-instance`
