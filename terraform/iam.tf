# 
# admin deployment
# 

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }

    # condition {
    #   test     = "StringEquals"
    #   variable = "aws:SourceAccount"
    #   values   = [
    #     local.account
    #   ]
    # }
  }
}

resource "aws_iam_role" "theunending_admin" {
  name               = "theunending-admin"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = {
    Name = "theunending-admin"
  }
}

resource "aws_iam_instance_profile" "theunending_admin" {
  name = "theunending-admin-profile"
  role = aws_iam_role.theunending_admin.name
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.theunending_admin.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "app_permissions" {
  statement {
    sid       = "GetAuthorizationToken"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "ReadRepositoryContents"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:ListImages",
    ]
    resources = [
      "arn:aws:ecr:us-east-1:396610714890:repository/theunending/*"
    ]
  }

  statement {
    sid    = "ListBucketMetadata"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      "arn:aws:s3:::wrossmorrow-genai-repetitions-use1",
      "arn:aws:s3:::theunending-ai-raw-content-use1"
    ]
  }

  statement {
    sid    = "ReadBucketObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
    ]
    resources = [
      "arn:aws:s3:::wrossmorrow-genai-repetitions-use1/*",
      "arn:aws:s3:::theunending-ai-raw-content-use1/*"
    ]
  }

  statement {
    sid    = "ListBucketAndUploads"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:ListBucketMultipartUploads",
    ]
    resources = [
      "arn:aws:s3:::theunending-ai-site-content-use1"
    ]
  }

  statement {
    sid    = "ReadWriteBucketObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "arn:aws:s3:::theunending-ai-raw-content-use1/*",
      "arn:aws:s3:::theunending-ai-site-content-use1/*",
    ]
  }

  statement {
    sid    = "PublishAdminNotifications"
    effect = "Allow"
    actions = [
      "sns:Publish",
    ]
    resources = [
      aws_sns_topic.admin_notifications.arn,
    ]
  }
}

resource "aws_iam_role_policy" "app_permissions" {
  name   = "theunending-ecr-s3-access"
  role   = aws_iam_role.theunending_admin.id
  policy = data.aws_iam_policy_document.app_permissions.json
}

# Modal

data "aws_iam_policy_document" "modal_oidc" {
  statement {
    effect  = "Allow"
    actions = [
      "sts:AssumeRoleWithWebIdentity",
    ]

    principals {
      type        = "Federated"
      identifiers = [
        "arn:aws:iam::396610714890:oidc-provider/oidc.modal.com",
      ]
    }

    condition {
      test = "StringEquals"
      variable = "oidc.modal.com:aud"
      values = ["oidc.modal.com"]
    }
    condition {
      test = "StringLike"
      variable = "oidc.modal.com:sub"
      values = ["modal:workspace_id:ac-CUGZoMZ8GV9XJHWy1qggIn:*"]
    }
  }
}

resource "aws_iam_role" "modal_oidc" {
  name               = "modal-oidc-access"
  assume_role_policy = data.aws_iam_policy_document.modal_oidc.json

  max_session_duration = 7200

  tags = {
    Name = "modal-oidc-access"
  }
}

data "aws_iam_policy_document" "modal_apps" {

  statement {
    sid    = "ListBucketAndUploads"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:ListBucketMultipartUploads",
    ]
    resources = [
      "arn:aws:s3:::wrossmorrow-genai-repetitions-use1",
      "arn:aws:s3:::theunending-ai-raw-content-use1"
    ]
  }

  statement {
    sid    = "ReadWriteBucketObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "arn:aws:s3:::wrossmorrow-genai-repetitions-use1/*",
      "arn:aws:s3:::theunending-ai-raw-content-use1/*"
    ]
  }
}

resource "aws_iam_role_policy" "modal_apps" {
  name   = "modal-oidc-access"
  role   = aws_iam_role.modal_oidc.id
  policy = data.aws_iam_policy_document.modal_apps.json
}

# 
# publish task
# 

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = [
      "sts:AssumeRole"
    ]

    principals {
      type        = "Service"
      identifiers = [
        "ecs-tasks.amazonaws.com"
      ]
    }

    # Only tasks in this account can assume these roles.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [
        local.account
      ]
    }
  }
}

# Execution role: used by ECS itself to pull the image, ship logs, inject the secret.

resource "aws_iam_role" "execution" {
  name               = "theunending-publish-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secret" {
  statement {
    actions   = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [
      data.aws_secretsmanager_secret.admin_api_auth.arn,
      data.aws_secretsmanager_secret.theunending_publish_github_app.arn,
      data.aws_secretsmanager_secret.theunending_publish_github_app_key.arn,
    ]
  }
}

resource "aws_iam_role_policy" "execution_secret" {
  name   = "read-admin-api-token"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secret.json
}

resource "aws_iam_role" "publish_task" {
  name               = "theunending-publish-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "publish_task_s3" {

  statement {
    sid       = "List"
    actions   = [
      "s3:ListBucket"
    ]
    resources = [
      "arn:aws:s3:::wrossmorrow-genai-repetitions-use1",
      "arn:aws:s3:::theunending-ai-raw-content-use1",
      "arn:aws:s3:::theunending-ai-site-content-use1",
    ]
  }
  
  statement {
    sid       = "ReadRunsAndSite"
    actions   = [
      "s3:GetObject",
    ]
    resources = [
      "arn:aws:s3:::wrossmorrow-genai-repetitions-use1/runs/*",
      "arn:aws:s3:::theunending-ai-raw-content-use1/runs/*",
      "arn:aws:s3:::theunending-ai-site-content-use1/*",
    ]
  }

  # Destination: PutObject (incl. IfNoneMatch conditional writes and copy targets),
  # GetObject so a 412 can be compared against what's already there.
  statement {
    sid       = "WriteSitePrefixes"
    actions   = ["s3:PutObject"]
    resources = [
      "arn:aws:s3:::theunending-ai-raw-content-use1/*",
      "arn:aws:s3:::theunending-ai-site-content-use1/drafts/*",
      "arn:aws:s3:::theunending-ai-site-content-use1/assets/*",
    ]
  }
  
  statement {
    sid       = "AssetsAreWriteOnce"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::theunending-ai-site-content-use1/assets/*"]
    condition {
      test     = "Null"
      variable = "s3:if-none-match"
      values   = ["true"]
    }
  }

  # Deliberately no s3:DeleteObject anywhere.
}

resource "aws_iam_role_policy" "task_s3" {
  name   = "theunending-publish"
  role   = aws_iam_role.publish_task.id
  policy = data.aws_iam_policy_document.publish_task_s3.json
}

# --- Launch permissions for the admin API -----------------------------------

data "aws_iam_policy_document" "launcher" {
  statement {
    sid     = "RunPublishTask"
    actions = [
      "ecs:RunTask",
    ]
    # Any revision of this family, so new image deploys don't need IAM changes.
    resources = ["${aws_ecs_task_definition.publish.arn_without_revision}:*"]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.publish.arn]
    }
  }

  statement {
    sid       = "WatchPublishTasks"
    actions   = [
      "ecs:DescribeTasks",
      "ecs:StopTask",
    ]
    # DescribeTasks / StopTask: tasks in the cluster
    resources = ["${replace(aws_ecs_cluster.publish.arn, ":cluster/", ":task/")}/*"]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.publish.arn]
    }
  }

  # The classic missing piece: RunTask hands both roles to ECS.
  statement {
    sid       = "PassPublishRoles"
    actions   = ["iam:PassRole"]
    resources = [
      aws_iam_role.execution.arn,
      aws_iam_role.publish_task.arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "launcher" {
  name        = "theunending-publish-launcher"
  description = "Start, inspect and stop theunending-publish tasks"
  policy      = data.aws_iam_policy_document.launcher.json
}

resource "aws_iam_role_policy_attachment" "launcher" {
  role       = aws_iam_role.theunending_admin.name
  policy_arn = aws_iam_policy.launcher.arn
}

#
# github actions
# 

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [
        aws_iam_openid_connect_provider.github.arn,
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = [
        "sts.amazonaws.com",
      ]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [
        "repo:wrossmorrow/theunending:ref:refs/heads/main",
      ]
    }
  }
}

data "aws_iam_policy_document" "github_actions" {

  statement {
    sid    = "ListBucketAndUploads"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:ListBucketMultipartUploads",
    ]
    resources = [
      "arn:aws:s3:::theunending-ai-site-content-use1"
    ]
  }

  statement {
    sid    = "ReadWriteBucketObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "arn:aws:s3:::theunending-ai-site-content-use1/*"
    ]
  }
}

resource "aws_iam_policy" "github_actions" {
  name   = "theunending-github-actions-access"
  policy = data.aws_iam_policy_document.github_actions.json
}

resource "aws_iam_role" "github_actions" {
  name               = "theunending-github-actions-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json
}

resource "aws_iam_role_policy_attachment" "github_actions" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.github_actions.arn
}
