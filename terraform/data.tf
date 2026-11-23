
data "aws_secretsmanager_secret" "admin_api_auth" {
  name = "theunending-admin-api-auth"
}

data "aws_secretsmanager_secret" "theunending_publish_github_app" {
  name = "theunending-publish-github-app"
}

data "aws_secretsmanager_secret" "theunending_publish_github_app_key" {
  name = "theunending-publish-github-app-key"
}
