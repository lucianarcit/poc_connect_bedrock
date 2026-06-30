# --- CloudWatch Log Groups (POC Bedrock) ---

resource "aws_cloudwatch_log_group" "initializer" {
  name              = "/aws/lambda/${local.initializer_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "integrator" {
  name              = "/aws/lambda/${local.integrator_name}"
  retention_in_days = var.log_retention_days
}

# --- Metric Filter: FailedFinal ---

resource "aws_cloudwatch_log_metric_filter" "failed_final" {
  name           = "${local.name}-failed-final"
  log_group_name = aws_cloudwatch_log_group.integrator.name
  pattern        = "{ $.metric = \"FailedFinal\" }"

  metric_transformation {
    name      = "FailedFinalCount"
    namespace = "${local.prefix}/${var.environment_name}"
    value     = "1"
    unit      = "Count"
  }
}

# --- SNS Topic para Alarmes (opcional) ---

resource "aws_sns_topic" "alarms" {
  count = var.alarm_email != "" ? 1 : 0
  name  = "${local.name}-alarms"
}

resource "aws_sns_topic_subscription" "alarm_email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# --- Alarmes ---

locals {
  alarm_actions = var.alarm_email != "" ? [aws_sns_topic.alarms[0].arn] : []
}

# Alarme: FailedFinal
resource "aws_cloudwatch_metric_alarm" "failed_final" {
  alarm_name          = "${local.name}-failed-final"
  alarm_description   = "Mensagens marcadas FAILED_FINAL no Integrator"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FailedFinalCount"
  namespace           = "${local.prefix}/${var.environment_name}"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# Alarme: DLQ não vazia
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${local.name}-dlq-not-empty"
  alarm_description   = "Mensagens presentes na DLQ (falhas após ${var.sqs_max_receive_count} tentativas)"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# Alarme: Erros Lambda Initializer
resource "aws_cloudwatch_metric_alarm" "initializer_errors" {
  alarm_name          = "${local.name}-initializer-errors"
  alarm_description   = "Erros na Lambda Initializer"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 2
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.initializer.function_name
  }

  alarm_actions = local.alarm_actions
}

# Alarme: Erros Lambda Integrator
resource "aws_cloudwatch_metric_alarm" "integrator_errors" {
  alarm_name          = "${local.name}-integrator-errors"
  alarm_description   = "Erros na Lambda Integrator"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 2
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.integrator.function_name
  }

  alarm_actions = local.alarm_actions
}

# Alarme: Throttling Lambda Integrator
resource "aws_cloudwatch_metric_alarm" "integrator_throttles" {
  alarm_name          = "${local.name}-integrator-throttles"
  alarm_description   = "Throttling na Lambda Integrator"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.integrator.function_name
  }

  alarm_actions = local.alarm_actions
}

# Alarme: Idade da mensagem mais antiga na SQS
resource "aws_cloudwatch_metric_alarm" "sqs_oldest_message" {
  alarm_name          = "${local.name}-sqs-oldest-message"
  alarm_description   = "Mensagem mais antiga na SQS > 5 minutos"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 300
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.messages.name
  }

  alarm_actions = local.alarm_actions
}
