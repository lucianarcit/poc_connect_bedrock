# --- Event Source Mapping: SQS → Lambda Integrator ---
#
# Configuração:
# - batch_size conservador para a POC
# - ReportBatchItemFailures habilitado (partial batch response)
# - maximum_batching_window_seconds = 0 (sem agrupar por tempo)
# - Sem filtro de eventos (todos os registros SQS são processados)

resource "aws_lambda_event_source_mapping" "sqs_to_integrator" {
  event_source_arn = aws_sqs_queue.messages.arn
  function_name    = aws_lambda_function.integrator.arn
  enabled          = true

  batch_size                         = var.integrator_batch_size # 5
  maximum_batching_window_in_seconds = 0

  function_response_types = ["ReportBatchItemFailures"]
}
