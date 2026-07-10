# --- Lambda: Initializer ---

resource "aws_lambda_function" "initializer" {
  function_name = local.initializer_name
  role          = aws_iam_role.initializer.arn
  handler       = "initializer.handler.handler"
  runtime       = local.lambda_runtime
  timeout       = var.initializer_timeout # 8s
  memory_size   = var.lambda_memory_mb
  architectures = ["x86_64"]

  filename         = "${path.module}/../packages/initializer.zip"
  source_code_hash = filebase64sha256("${path.module}/../packages/initializer.zip")

  environment {
    variables = {
      SNS_TOPIC_ARN       = aws_sns_topic.streaming.arn
      KMS_KEY_ID          = aws_kms_key.tokens.key_id
      SESSIONS_TABLE_NAME = aws_dynamodb_table.sessions.name
      CONNECT_INSTANCE_ID = var.connect_instance_id
    }
  }

  depends_on = [aws_cloudwatch_log_group.initializer]
}

# --- Lambda Permission: Allow Amazon Connect to invoke Initializer ---

resource "aws_lambda_permission" "allow_connect_invoke_initializer" {
  statement_id   = "AllowConnectInvoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.initializer.function_name
  principal      = "connect.amazonaws.com"
  source_arn     = "arn:aws:connect:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:instance/${var.connect_instance_id}"
  source_account = data.aws_caller_identity.current.account_id
}

# --- Lambda: Integrator (Bedrock Converse) ---

resource "aws_lambda_function" "integrator" {
  function_name = local.integrator_name
  role          = aws_iam_role.integrator.arn
  handler       = "integrator.handler.handler"
  runtime       = local.lambda_runtime
  timeout       = var.integrator_timeout # 60s
  memory_size   = var.lambda_memory_mb
  architectures = ["x86_64"]

  filename         = "${path.module}/../packages/integrator.zip"
  source_code_hash = filebase64sha256("${path.module}/../packages/integrator.zip")

  environment {
    variables = {
      SESSIONS_TABLE_NAME     = aws_dynamodb_table.sessions.name
      IDEMPOTENCY_TABLE_NAME  = aws_dynamodb_table.idempotency.name
      KMS_KEY_ID              = aws_kms_key.tokens.key_id
      LEASE_DURATION_SECONDS  = tostring(var.lease_duration_seconds)
      BEDROCK_MODEL_ID        = var.bedrock_model_id
      BEDROCK_MAX_TOKENS      = tostring(var.bedrock_max_tokens)
      BEDROCK_TEMPERATURE     = tostring(var.bedrock_temperature)
      BEDROCK_SYSTEM_PROMPT   = var.bedrock_system_prompt
      BEDROCK_TIMEOUT_SECONDS = tostring(var.bedrock_timeout_seconds)
    }
  }

  depends_on = [aws_cloudwatch_log_group.integrator]
}
