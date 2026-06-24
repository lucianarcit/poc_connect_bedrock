variable "aws_region" {
  description = "Região AWS para provisionamento."
  type        = string
  default     = "us-east-1"
}

variable "environment_name" {
  description = "Nome do ambiente (ex: dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "connect_instance_id" {
  description = "ID da instância Amazon Connect existente."
  type        = string
}

variable "connect_instance_arn" {
  description = "ARN da instância Amazon Connect existente."
  type        = string
}

variable "connect_contact_flow_id" {
  description = "ID do Contact Flow (opcional; usado em outputs e documentação)."
  type        = string
  default     = ""
}

variable "alarm_email" {
  description = "E-mail para receber alarmes via SNS (opcional; se vazio, alarmes não criam subscription)."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "Dias de retenção dos logs no CloudWatch."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags adicionais a serem aplicadas em todos os recursos."
  type        = map(string)
  default     = {}
}

# --- Configurações de timing ---

variable "integrator_timeout" {
  description = "Timeout da Lambda Integrator em segundos."
  type        = number
  default     = 60
}

variable "initializer_timeout" {
  description = "Timeout da Lambda Initializer em segundos."
  type        = number
  default     = 8
}

variable "mcp_server_timeout" {
  description = "Timeout da Lambda MCP Server em segundos."
  type        = number
  default     = 30
}

variable "sqs_visibility_timeout" {
  description = "SQS VisibilityTimeout em segundos (recomendado: 6x Lambda timeout)."
  type        = number
  default     = 360
}

variable "sqs_max_receive_count" {
  description = "Número máximo de recebimentos antes de enviar para DLQ."
  type        = number
  default     = 3
}

variable "sqs_retention_days" {
  description = "Retenção de mensagens na SQS principal (dias)."
  type        = number
  default     = 4
}

variable "dlq_retention_days" {
  description = "Retenção de mensagens na DLQ (dias)."
  type        = number
  default     = 14
}

variable "session_ttl_hours" {
  description = "TTL das sessões no DynamoDB (horas)."
  type        = number
  default     = 24
}

variable "idempotency_ttl_hours" {
  description = "TTL dos registros de idempotência no DynamoDB (horas)."
  type        = number
  default     = 24
}

variable "lease_duration_seconds" {
  description = "Duração do lease de idempotência em segundos."
  type        = number
  default     = 90
}

variable "integrator_batch_size" {
  description = "Tamanho do batch SQS → Lambda Integrator."
  type        = number
  default     = 5
}

variable "lambda_memory_mb" {
  description = "Memória alocada para as Lambdas (MB)."
  type        = number
  default     = 256
}
