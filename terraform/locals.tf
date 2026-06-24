locals {
  prefix = "connect-mcp-poc"
  name   = "${local.prefix}-${var.environment_name}"

  common_tags = merge(var.tags, {
    Project     = "amazon-connect-mcp-poc"
    Environment = var.environment_name
    ManagedBy   = "terraform"
  })

  # Nomes de recursos
  sns_topic_name       = "${local.name}-streaming"
  sqs_queue_name       = "${local.name}-messages"
  sqs_dlq_name         = "${local.name}-messages-dlq"
  sessions_table_name  = "${local.name}-sessions"
  idemp_table_name     = "${local.name}-idempotency"
  kms_alias            = "alias/${local.name}-tokens"

  # Lambdas
  initializer_name = "${local.name}-initializer"
  integrator_name  = "${local.name}-integrator"
  mcp_server_name  = "${local.name}-mcp-server"

  # Timings
  session_ttl_seconds     = var.session_ttl_hours * 3600
  idempotency_ttl_seconds = var.idempotency_ttl_hours * 3600
  sqs_retention_seconds   = var.sqs_retention_days * 86400
  dlq_retention_seconds   = var.dlq_retention_days * 86400

  # Lambda runtime — Python 3.12 (última versão estável disponível na AWS Lambda)
  lambda_runtime = "python3.12"
}
