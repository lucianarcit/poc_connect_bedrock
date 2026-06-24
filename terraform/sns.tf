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
