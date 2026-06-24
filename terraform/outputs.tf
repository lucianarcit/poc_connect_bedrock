output "sns_topic_arn" {
  description = "ARN do SNS Topic para configurar no StartContactStreaming."
  value       = aws_sns_topic.streaming.arn
}

output "sqs_queue_url" {
  description = "URL da SQS principal."
  value       = aws_sqs_queue.messages.url
}

output "sqs_dlq_url" {
  description = "URL da DLQ."
  value       = aws_sqs_queue.dlq.url
}

output "sessions_table_name" {
  description = "Nome da tabela DynamoDB de sessões."
  value       = aws_dynamodb_table.sessions.name
}

output "idempotency_table_name" {
  description = "Nome da tabela DynamoDB de idempotência."
  value       = aws_dynamodb_table.idempotency.name
}

output "kms_key_arn" {
  description = "ARN da chave KMS para criptografia de tokens."
  value       = aws_kms_key.tokens.arn
}

output "initializer_lambda_arn" {
  description = "ARN da Lambda Initializer."
  value       = aws_lambda_function.initializer.arn
}

output "integrator_lambda_arn" {
  description = "ARN da Lambda Integrator."
  value       = aws_lambda_function.integrator.arn
}

output "mcp_server_lambda_arn" {
  description = "ARN da Lambda MCP Server."
  value       = aws_lambda_function.mcp_server.arn
}

output "mcp_server_function_url" {
  description = "URL da Function URL do MCP Server (HTTPS, protegida por AWS_IAM)."
  value       = aws_lambda_function_url.mcp_server.function_url
}

output "connect_instance_id" {
  description = "ID da instância Connect (passthrough para referência)."
  value       = var.connect_instance_id
}
