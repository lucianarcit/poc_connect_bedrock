# --- DynamoDB: Sessões ---

resource "aws_dynamodb_table" "sessions" {
  name         = local.sessions_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false # POC — habilitar em produção
  }

  server_side_encryption {
    enabled = true # Usa chave default gerenciada pelo DynamoDB (aws/dynamodb)
  }
}

# --- DynamoDB: Idempotência ---

resource "aws_dynamodb_table" "idempotency" {
  name         = local.idemp_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  server_side_encryption {
    enabled = true # Usa chave default gerenciada pelo DynamoDB (aws/dynamodb)
  }
}
