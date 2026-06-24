# Checklist de Implantação — Versão Reduzida

> Versão imprimível. Detalhes completos em [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

## Fase 1 — Preparação Local

- [ ] `python --version` → 3.12+
- [ ] `terraform -version` → >= 1.6
- [ ] `aws --version` → v2
- [ ] `aws sts get-caller-identity` → conta correta
- [ ] `.venv` ativado
- [ ] `pip install -r requirements-dev.txt`
- [ ] `python -m pytest` → 241 passed, ≥80% coverage
- [ ] `.\scripts\build_lambdas.ps1` → 3 ZIPs em `packages/`

## Fase 2 — Terraform

- [ ] `cd terraform`
- [ ] `Copy-Item terraform.tfvars.example terraform.tfvars`
- [ ] Preencher `connect_instance_id` e `connect_instance_arn`
- [ ] `terraform fmt -recursive`
- [ ] `terraform init`
- [ ] `terraform validate` → "Success!"
- [ ] `terraform plan -out=tfplan` → ~30 recursos
- [ ] Revisar plan
- [ ] ⚠️ `terraform apply tfplan`
- [ ] `terraform output` → guardar ARNs

## Fase 3 — Amazon Connect (Manual)

- [ ] Autorizar Lambda: Console Connect → Contact flows → AWS Lambda → colar `initializer_lambda_arn`
- [ ] Criar Contact Flow `MCP-POC-Chat-Flow`
- [ ] Bloco "Invoke AWS Lambda" → Initializer, timeout 8s
- [ ] Success → Wait; Error → Disconnect
- [ ] Publicar flow
- [ ] Criar Hosted Chat Widget → associar ao flow
- [ ] Domínio permitido: `http://localhost:8080`
- [ ] Confirmar e-mail de alarme (se configurado)

## Fase 4 — Teste

- [ ] `python -m http.server 8080` (servir página com widget)
- [ ] Abrir chat → enviar "qual o status"
- [ ] Verificar resposta do bot
- [ ] Verificar CloudWatch logs (sem erros)
- [ ] Verificar DLQ vazia

## Fase 5 — Encerramento (quando decidido)

- [ ] Salvar evidências
- [ ] Remover widget e flow no Connect
- [ ] Remover autorização Lambda no Connect
- [ ] `terraform plan -destroy`
- [ ] ⚠️ `terraform destroy`
- [ ] Opcional: `aws connect delete-instance`
