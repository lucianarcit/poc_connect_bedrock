# --- IAM: Roles e Policies para as Lambdas (POC Bedrock) ---
#
# Princípios:
# - Least privilege: cada Lambda recebe somente os acessos necessários.
# - Resource específico: nenhum Resource = "*" sem justificativa documentada.
# - KMS: delegação via IAM (key policy permite root, policies restringem por ARN).
# - Connect: APIs StartContactStreaming, CreateParticipant requerem Resource = "*"
#   porque a API não suporta resource-level permissions.
# - Bedrock: bedrock:InvokeModel com ARN parametrizado (var.bedrock_model_arn).
#
# Governança da conta:
# - Sufixo obrigatório: -PPD
# - Permissions Boundary: ContributorBoundaryPolicy-ITSM-145407
# - Tag obrigatória: Project = "AWS-PPD"

# ============================================================================
# INITIALIZER
# ============================================================================

resource "aws_iam_role" "initializer" {
  name                 = local.initializer_role_name
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume.json
  permissions_boundary = local.permissions_boundary_arn

  tags = {
    Project = "AWS-PPD"
  }
}

resource "aws_iam_role_policy" "initializer" {
  name   = "${local.initializer_name}-policy"
  role   = aws_iam_role.initializer.id
  policy = data.aws_iam_policy_document.initializer_policy.json
}

resource "aws_iam_role_policy_attachment" "initializer_basic" {
  role       = aws_iam_role.initializer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "initializer_policy" {
  # DynamoDB: Sessions table (PutItem, GetItem, UpdateItem)
  statement {
    sid    = "DynamoDBSessions"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.sessions.arn]
  }

  # KMS: Encrypt tokens (criptografa ParticipantToken e ConnectionToken)
  statement {
    sid    = "KMSEncrypt"
    effect = "Allow"
    actions = [
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.tokens.arn]
  }

  # Amazon Connect: StartContactStreaming, CreateParticipant
  # Resource = "*" justificativa: estas APIs não suportam resource-level permissions.
  statement {
    sid    = "ConnectStreaming"
    effect = "Allow"
    actions = [
      "connect:StartContactStreaming",
      "connect:CreateParticipant",
    ]
    resources = ["*"]
  }
}

# ============================================================================
# INTEGRATOR (Bedrock Converse)
# ============================================================================

resource "aws_iam_role" "integrator" {
  name                 = local.integrator_role_name
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume.json
  permissions_boundary = local.permissions_boundary_arn

  tags = {
    Project = "AWS-PPD"
  }
}

resource "aws_iam_role_policy" "integrator" {
  name   = "${local.integrator_name}-policy"
  role   = aws_iam_role.integrator.id
  policy = data.aws_iam_policy_document.integrator_policy.json
}

resource "aws_iam_role_policy_attachment" "integrator_basic" {
  role       = aws_iam_role.integrator.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "integrator_policy" {
  # SQS: receber e deletar mensagens da fila principal
  statement {
    sid    = "SQSConsume"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.messages.arn]
  }

  # DynamoDB: Sessions table (GetItem, UpdateItem para token renewal)
  statement {
    sid    = "DynamoDBSessions"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.sessions.arn]
  }

  # DynamoDB: Idempotency table (PutItem, GetItem, UpdateItem)
  statement {
    sid    = "DynamoDBIdempotency"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.idempotency.arn]
  }

  # KMS: Decrypt/Encrypt tokens
  statement {
    sid    = "KMSDecryptEncrypt"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.tokens.arn]
  }

  # Amazon Bedrock: InvokeModel
  # Resource: ARN obrigatorio fornecido via var.bedrock_model_arn.
  # Wildcard NAO e gerado automaticamente. Se necessario, o operador deve
  # fornecer explicitamente o ARN wildcard e documentar a justificativa.
  statement {
    sid    = "BedrockInvokeModel"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
    ]
    resources = [var.bedrock_model_arn]
  }
}

# ============================================================================
# SHARED: Assume Role Policy para Lambda
# ============================================================================

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    sid    = "LambdaAssumeRole"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}
