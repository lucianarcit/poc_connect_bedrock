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

# --- Lambda: Integrator ---

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
      SESSIONS_TABLE_NAME    = aws_dynamodb_table.sessions.name
      IDEMPOTENCY_TABLE_NAME = aws_dynamodb_table.idempotency.name
      KMS_KEY_ID             = aws_kms_key.tokens.key_id
      MCP_SERVER_URL         = aws_lambda_function_url.mcp_server.function_url
      LEASE_DURATION_SECONDS = tostring(var.lease_duration_seconds)
      MCP_TIMEOUT_SECONDS    = "10"
      MCP_MAX_RETRIES        = "2"
    }
  }

  depends_on = [aws_cloudwatch_log_group.integrator]
}

# --- Lambda: MCP Server ---

resource "aws_lambda_function" "mcp_server" {
  function_name = local.mcp_server_name
  role          = aws_iam_role.mcp_server.arn
  handler       = "mcp_server.handler.handler"
  runtime       = local.lambda_runtime
  timeout       = var.mcp_server_timeout # 30s
  memory_size   = var.lambda_memory_mb
  architectures = ["x86_64"]

  filename         = "${path.module}/../packages/mcp_server.zip"
  source_code_hash = filebase64sha256("${path.module}/../packages/mcp_server.zip")

  environment {
    variables = {
      SAMPLE_DOCUMENTS_DIR = "/var/task/sample_documents"
    }
  }

  depends_on = [aws_cloudwatch_log_group.mcp_server]
}
