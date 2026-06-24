# --- IAM: Roles e Policies para as Lambdas ---
#
# Princípios:
# - Least privilege: cada Lambda recebe somente os acessos necessários.
# - Resource específico: nenhum Resource = "*" sem justificativa.
# - KMS: delegação via IAM (key policy permite root, policies restringem por ARN).
# - Connect: APIs connect:StartContactStreaming, connect:CreateParticipant
#   requerem Resource = "*" porque a API não suporta resource-level permissions.
#   Ref: https://docs.aws.amazon.com/connect/latest/adminguide/security-iam.html
# - connectparticipant:* NÃO usa IAM/SigV4 (autenticado por token), portanto NÃO incluído.

# ============================================================================
# INITIALIZER
# ============================================================================

resource "aws_iam_role" "initializer" {
  name = "${local.initializer_name}-role"

  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
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
  # A instância é validada pelo código (connect_instance_id env var).
  statement {
    sid    = "ConnectStreaming"
    effect = "Allow"
    actions = [
      "connect:StartContactStreaming",
      "connect:CreateParticipant",
    ]
    resources = ["*"]
  }

  # connectparticipant:* NÃO necessário:
  # CreateParticipantConnection usa ParticipantToken (não IAM/SigV4).
}

# ============================================================================
# INTEGRATOR
# ============================================================================

resource "aws_iam_role" "integrator" {
  name = "${local.integrator_name}-role"

  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
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

  # KMS: Decrypt tokens (descriptografa ConnectionToken para SendMessage)
  # e Encrypt (quando renova token e persiste novo)
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

  # connectparticipant:* NÃO necessário:
  # SendMessage e CreateParticipantConnection usam ConnectionToken/ParticipantToken (não IAM/SigV4).

  # Lambda: Invocar MCP Server exclusivamente via Function URL (SigV4)
  # Duas ações distintas com condições específicas:

  # 1. InvokeFunctionUrl — condição: somente Function URLs com auth AWS_IAM
  statement {
    sid    = "InvokeMCPServerFunctionUrl"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunctionUrl",
    ]
    resources = [aws_lambda_function.mcp_server.arn]

    condition {
      test     = "StringEquals"
      variable = "lambda:FunctionUrlAuthType"
      values   = ["AWS_IAM"]
    }
  }

  # 2. InvokeFunction — condição: somente quando invocado via Function URL
  #    Impede InvokeFunction direto (SDK/CLI) sem passar pela Function URL.
  statement {
    sid    = "InvokeMCPServerOnlyViaUrl"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [aws_lambda_function.mcp_server.arn]

    condition {
      test     = "Bool"
      variable = "lambda:InvokedViaFunctionUrl"
      values   = ["true"]
    }
  }
}

# ============================================================================
# MCP SERVER
# ============================================================================

resource "aws_iam_role" "mcp_server" {
  name = "${local.mcp_server_name}-role"

  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "mcp_server_basic" {
  role       = aws_iam_role.mcp_server.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# MCP Server não precisa de policy adicional para a POC:
# - Lê apenas sample_documents empacotados localmente
# - Não acessa DynamoDB, KMS, Connect, SQS
# - Logs cobertos pelo AWSLambdaBasicExecutionRole

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
