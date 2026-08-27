terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }
}

variable "name" { type = string }

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-jobs-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${var.name}-jobs"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 10
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}

output "queue_name" { value = aws_sqs_queue.jobs.name }
output "queue_url" { value = aws_sqs_queue.jobs.url }
output "queue_arn" { value = aws_sqs_queue.jobs.arn }
output "dlq_name" { value = aws_sqs_queue.dlq.name }
output "dlq_arn" { value = aws_sqs_queue.dlq.arn }
output "dlq_url" { value = aws_sqs_queue.dlq.url }
