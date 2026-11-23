data "google_project" "current" {
  project_id = var.gcp_project_id
}

locals {
  enabled_apis = toset([
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
  ])

  pool_resource_name = "projects/${data.google_project.current.number}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.workloads.workload_identity_pool_id}"

  aws_wif_provider_name   = "${local.pool_resource_name}/providers/${google_iam_workload_identity_pool_provider.aws.workload_identity_pool_provider_id}"
  modal_wif_provider_name = "${local.pool_resource_name}/providers/${google_iam_workload_identity_pool_provider.modal.workload_identity_pool_provider_id}"

  admin_aws_principal_set   = "principalSet://iam.googleapis.com/${local.pool_resource_name}/attribute.aws_role/${var.aws_admin_role_name}"
  publish_aws_principal_set = "principalSet://iam.googleapis.com/${local.pool_resource_name}/attribute.aws_role/${var.aws_publish_role_name}"
  modal_principal_set       = "principalSet://iam.googleapis.com/${local.pool_resource_name}/attribute.workspace_id/${var.modal_workspace_id}"
}

resource "google_project_service" "apis" {
  for_each           = local.enabled_apis
  project            = var.gcp_project_id
  service            = each.value
  disable_on_destroy = false
}

# Zero-permission service accounts: they hold no GCP IAM roles on any project/resource.
# External callers impersonate them solely to mint Google OIDC ID tokens.

resource "google_service_account" "admin_api" {
  account_id   = "admin-api"
  display_name = "The Unending Admin API (EC2 -> Modal)"
  description  = "Zero-GCP-permission SA impersonated via AWS WIF by the admin EC2 role."
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "modal_jobs" {
  account_id   = "modal-jobs"
  display_name = "The Unending Modal Jobs (Modal -> Envoy)"
  description  = "Zero-GCP-permission SA impersonated via Modal OIDC WIF by Modal jobs."
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "publish_job" {
  account_id   = "publish-job"
  display_name = "The Unending Publish Task (Fargate -> Envoy)"
  description  = "Zero-GCP-permission SA impersonated via AWS WIF by ECS Fargate publish tasks."
  depends_on   = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool" "workloads" {
  workload_identity_pool_id = var.pool_id
  display_name              = "The Unending Workloads"
  description               = "Federates AWS (EC2, ECS Fargate) and Modal workloads without SA keys."
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "aws" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.workloads.workload_identity_pool_id
  workload_identity_pool_provider_id = "aws"
  display_name                       = "AWS Workloads"
  description                        = "Trusts assumed-role credentials from the admin EC2 and publish Fargate roles."

  aws {
    account_id = var.aws_account_id
  }

  attribute_mapping = {
    "google.subject"        = "assertion.arn"
    "attribute.aws_account" = "assertion.account"
    "attribute.aws_role"    = "assertion.arn.extract('assumed-role/{role}/')"
  }

  attribute_condition = "assertion.account == '${var.aws_account_id}' && (assertion.arn.startsWith('arn:aws:sts::${var.aws_account_id}:assumed-role/${var.aws_admin_role_name}/') || assertion.arn.startsWith('arn:aws:sts::${var.aws_account_id}:assumed-role/${var.aws_publish_role_name}/'))"
}

resource "google_iam_workload_identity_pool_provider" "modal" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.workloads.workload_identity_pool_id
  workload_identity_pool_provider_id = "modal"
  display_name                       = "Modal Workloads"
  description                        = "Trusts Modal OIDC tokens from workspace ${var.modal_workspace_id}."

  oidc {
    issuer_uri        = "https://oidc.modal.com"
    allowed_audiences = ["oidc.modal.com"]
  }

  attribute_mapping = {
    "google.subject"         = "assertion.sub"
    "attribute.workspace_id" = "assertion.sub.extract('modal:workspace_id:{ws}:')"
  }

  attribute_condition = "assertion.sub.startsWith('modal:workspace_id:${var.modal_workspace_id}:')"
}

# Impersonation bindings (roles/iam.serviceAccountTokenCreator grants generateIdToken)

resource "google_service_account_iam_member" "admin_api_aws_token_creator" {
  service_account_id = google_service_account.admin_api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = local.admin_aws_principal_set
}

resource "google_service_account_iam_member" "modal_jobs_oidc_token_creator" {
  service_account_id = google_service_account.modal_jobs.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = local.modal_principal_set
}

resource "google_service_account_iam_member" "publish_job_aws_token_creator" {
  service_account_id = google_service_account.publish_job.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = local.publish_aws_principal_set
}

# Optional developer impersonation for local CLI scripts (batch-api.sh, finish-entrypoint.sh)

resource "google_service_account_iam_member" "developer_admin_api" {
  for_each           = toset(var.developer_emails)
  service_account_id = google_service_account.admin_api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${each.value}"
}

resource "google_service_account_iam_member" "developer_publish_job" {
  for_each           = toset(var.developer_emails)
  service_account_id = google_service_account.publish_job.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${each.value}"
}
