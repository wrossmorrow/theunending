
data "aws_secretsmanager_secret" "theunending_publish_github_app" {
  name = "theunending-publish-github-app"
}

data "aws_secretsmanager_secret" "theunending_publish_github_app_key" {
  name = "theunending-publish-github-app-key"
}
