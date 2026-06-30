# --- Locals: POC Bedrock Converse ---
#
# Prefixo: connect-bedrock-poc (independente da POC MCP)
# Este Terraform NÃO compartilha state, backend ou recursos com a POC MCP.

locals {
  prefix = "connect-bedrock-poc"
  name   = "${local.prefix}-${var.environment_name}"

  common_tags = merge(var.tags, {
    Project     = "amazon-connect-bedrock-poc"
    Environment = var.environment_name
    ManagedBy   = "terraform"
  })

  # Nomes de recursos
  sns_topic_name      = "${local.name}-streaming"
  sqs_queue_name      = "${local.name}-messages"
  sqs_dlq_name        = "${local.name}-messages-dlq"
  sessions_table_name = "${local.name}-sessions"
  idemp_table_name    = "${local.name}-idempotency"
  kms_alias           = "alias/${local.name}-tokens"

  # Lambdas
  initializer_name = "${local.name}-initializer"
  integrator_name  = "${local.name}-integrator"

  # IAM Roles — sufixo -PPD obrigatório por governança da conta
  initializer_role_name = "${local.name}-initializer-ExecutionRole-PPD"
  integrator_role_name  = "${local.name}-integrator-ExecutionRole-PPD"

  # Permissions Boundary obrigatória
  permissions_boundary_arn = "arn:aws:iam::253223147282:policy/ContributorBoundaryPolicy-ITSM-145407"

  # Timings
  session_ttl_seconds     = var.session_ttl_hours * 3600
  idempotency_ttl_seconds = var.idempotency_ttl_hours * 3600
  sqs_retention_seconds   = var.sqs_retention_days * 86400
  dlq_retention_seconds   = var.dlq_retention_days * 86400

  # Lambda runtime — Python 3.12
  lambda_runtime = "python3.12"
}
