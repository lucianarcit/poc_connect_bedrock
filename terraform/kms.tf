# --- KMS: Chave para criptografia de tokens (ParticipantToken, ConnectionToken) ---
#
# A key policy habilita apenas administração root + delegação via IAM.
# As permissões operacionais (Encrypt/Decrypt) são concedidas nas IAM policies
# das Lambdas (Etapa 4.5), apontando para o ARN exato desta chave.
#
# Isso evita dependência circular (roles ainda não existem quando a chave é criada).

resource "aws_kms_key" "tokens" {
  description             = "Criptografia de tokens do Amazon Connect para a POC Bedrock"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = data.aws_iam_policy_document.kms_key_policy.json
}

resource "aws_kms_alias" "tokens" {
  name          = local.kms_alias
  target_key_id = aws_kms_key.tokens.key_id
}

data "aws_iam_policy_document" "kms_key_policy" {
  # Permite administração pela conta root e habilita delegação via IAM policies.
  # Qualquer principal na conta pode usar a chave SE sua IAM policy permitir.
  statement {
    sid    = "EnableRootAccountAccessAndIAMDelegation"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    actions   = ["kms:*"]
    resources = ["*"]
  }
}
