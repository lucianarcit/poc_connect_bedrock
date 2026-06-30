# --- Variáveis de configuração: POC Bedrock Converse ---

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
  description = "ID do Contact Flow da POC Bedrock (separado do flow MCP)."
  type        = string
  default     = ""
}

variable "alarm_email" {
  description = "E-mail para receber alarmes via SNS (opcional)."
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

# --- Configurações do Amazon Bedrock ---

variable "bedrock_model_id" {
  description = "ID do modelo Bedrock para a Converse API. OBRIGATÓRIO — validar via smoke test antes do deploy."
  type        = string
  # Sem default — forçar operador a definir explicitamente após validação

  validation {
    condition     = length(var.bedrock_model_id) > 0
    error_message = "bedrock_model_id não pode ser vazio. Execute o smoke test para validar o modelo e forneça o ID explicitamente."
  }
}

variable "bedrock_model_arn" {
  description = "ARN do modelo ou inference profile para IAM policy. OBRIGATORIO — validar com aws bedrock get-foundation-model antes do deploy."
  type        = string
  # Sem default — forcar operador a definir explicitamente apos validacao real

  validation {
    condition     = length(var.bedrock_model_arn) > 0
    error_message = "bedrock_model_arn nao pode ser vazio. Valide o ARN com 'aws bedrock get-foundation-model' e forneca explicitamente."
  }
}

variable "bedrock_max_tokens" {
  description = "Número máximo de tokens na resposta da Converse API."
  type        = number
  default     = 1024

  validation {
    condition     = var.bedrock_max_tokens >= 1 && var.bedrock_max_tokens <= 4096
    error_message = "bedrock_max_tokens deve estar entre 1 e 4096."
  }
}

variable "bedrock_temperature" {
  description = "Temperature da geração (0.0 a 1.0)."
  type        = number
  default     = 0.7

  validation {
    condition     = var.bedrock_temperature >= 0.0 && var.bedrock_temperature <= 1.0
    error_message = "bedrock_temperature deve estar entre 0.0 e 1.0."
  }
}

variable "bedrock_system_prompt" {
  description = "System prompt para o modelo. Vazio = usar prompt padrão em pt-BR do BedrockClient."
  type        = string
  default     = ""
}

variable "bedrock_timeout_seconds" {
  description = "Timeout da chamada ao Bedrock em segundos. Deve ser <= (integrator_timeout - 5)."
  type        = number
  default     = 20

  validation {
    condition     = var.bedrock_timeout_seconds >= 5
    error_message = "bedrock_timeout_seconds deve ser >= 5."
  }
}
