# --- SNS: Topic para streaming de mensagens do Amazon Connect ---

resource "aws_sns_topic" "streaming" {
  name = local.sns_topic_name
}

# Subscription: SNS → SQS (RawMessageDelivery=false para manter envelope SNS com MessageAttributes)
resource "aws_sns_topic_subscription" "sqs" {
  topic_arn            = aws_sns_topic.streaming.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.messages.arn
  raw_message_delivery = false
}

# --- SNS Topic Policy: Permitir Amazon Connect publicar no tópico ---
#
# StartContactStreaming configura o Connect para publicar eventos de chat neste tópico.
# Sem esta policy, o Connect recebe AccessDenied ao tentar sns:Publish.
# Condições restringem ao account e à instância Connect específica.

resource "aws_sns_topic_policy" "allow_connect" {
  arn    = aws_sns_topic.streaming.arn
  policy = data.aws_iam_policy_document.sns_allow_connect.json
}

data "aws_iam_policy_document" "sns_allow_connect" {
  statement {
    sid    = "AllowConnectPublish"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["connect.amazonaws.com"]
    }

    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.streaming.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [var.connect_instance_arn]
    }
  }
}
