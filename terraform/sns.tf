# SNS topic for admin run status notifications (SNS -> email subscriptions).

resource "aws_sns_topic" "admin_notifications" {
  name         = "theunending-admin-notifications"
  display_name = "The Unending Admin Notifications"

  tags = {
    Name = "theunending-admin-notifications"
  }
}

# The email subscription starts in PendingConfirmation; the subscriber must confirm
# via the SNS confirmation email before published messages are delivered.

resource "aws_sns_topic_subscription" "admin_email" {
  topic_arn = aws_sns_topic.admin_notifications.arn
  protocol  = "email"
  endpoint  = var.admin_email_address
}
