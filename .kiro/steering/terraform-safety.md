---
inclusion: auto
---

# Terraform Safety

## Antes de qualquer plan

1. Rebuild das Lambdas alteradas: `.\scripts\build_lambdas.ps1 -Function <nome>`
2. Verificar que `packages/*.zip` existem e têm tamanho esperado
3. `terraform fmt -recursive`
4. `terraform validate`

## Antes de qualquer apply

1. Revisar o plan: `terraform show -no-color tfplan`
2. Verificar quantidade de add/change/destroy
3. **BLOQUEAR** se houver destroy ou replace sem justificativa explícita
4. Nunca usar `-auto-approve`
5. Nunca reutilizar plan salvo após alterar código ou rebuild

## Regras IAM desta conta

- Sufixo obrigatório: `-PPD`
- Permissions boundary: `arn:aws:iam::253223147282:policy/ContributorBoundaryPolicy-ITSM-145407`
- Tag obrigatória: `Project = "AWS-PPD"`

## Drift e ambiente apagado

Se o plan mostrar muitos creates (>10) ou destroys inesperados:
1. Verificar se o ambiente foi apagado fora do Terraform
2. Comparar state vs recursos reais: `terraform state list`
3. Não aplicar automaticamente — revisar cada recurso
