
resource "aws_ecs_cluster" "publish" {
  name = "theunending-publish"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "publish" {
  cluster_name       = aws_ecs_cluster.publish.name
  capacity_providers = ["FARGATE"]
}

resource "aws_cloudwatch_log_group" "publish" {
  name              = "/ecs/theunending"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "publish" {
  family                   = "theunending-publish"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 2048
  memory                   = 8192
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.publish_task.arn

  ephemeral_storage {
    size_in_gib = 50
  }

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([
    {
      name      = "publish"
      image     = local.image_ref
      essential = true

      # Overridden per launch: ["publish", "publish", "--run-id", "<run_id>"]
      command = [
        "publish",
        "--help",
      ]

      environment = [
        {
          name  = "GITHUB_API_BASE_URL",
          value = "https://api.github.com",
        },
        {
          name  = "GITHUB_REPO_OWNER",
          value = "wrossmorrow",
        },
        {
          name  = "GITHUB_REPO_NAME",
          value = "theunending",
        },
      ]

      secrets = [
        {
          name = "ADMIN_API_TOKEN", 
          valueFrom = "${data.aws_secretsmanager_secret.admin_api_auth.arn}:ADMIN_API_TOKEN::",
        },
        {
          name = "theunending-publish-github-app",
          valueFrom = "${data.aws_secretsmanager_secret.theunending_publish_github_app.arn}:GITHUB_APP_ID::",
        },
        {
          name = "theunending-publish-github-app-key",
          valueFrom = "${data.aws_secretsmanager_secret.theunending_publish_github_app_key.arn}:GITHUB_APP_PRIVATE_KEY::",
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.publish.name
          awslogs-region        = local.region
          awslogs-stream-prefix = "publish"
        }
      }
    }
  ])
}
