
data "aws_secretsmanager_secret" "admin_api_auth" {
  name = "theunending-admin-api-auth"
}
