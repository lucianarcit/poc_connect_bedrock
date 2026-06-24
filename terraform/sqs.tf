# --- SQS: Fila principal ---

resource "aws_sqs_queue" "messages" {
  name                       = local.sqs_queue_name
  visibility_timeout_seconds = var.sqs_visibility_timeout       # 360s (6x Lambda timeout)
  message_retention_seconds  = local.sqs_retention_seconds      # 4 dias
  receive_wait_time_seconds  = 20                               # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count             # 3
  })
}

# --- SQS: Dead-Letter Queue ---

resource "aws_sqs_queue" "dlq" {
  name                      = local.sqs_dlq_name
  message_retention_seconds = local.dlq_retention_seconds       # 14 dias
}

# --- SQS Policy: Permitir SNS publicar na fila principal ---

resource "aws_sqs_queue_policy" "allow_sns" {
  queue_url = aws_sqs_queue.messages.id

  policy = data.aws_iam_policy_document.sqs_allow_sns.json
}

data "aws_iam_policy_document" "sqs_allow_sns" {
  statement {
    sid    = "AllowSNSPublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }

    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.messages.arn]

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_sns_topic.streaming.arn]
    }
  }
}
