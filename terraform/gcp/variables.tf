variable "gcp_project_id" {
  description = "GCP project ID hosting the OAuth app and zero-permission machine service accounts."
  type        = string
}

variable "aws_account_id" {
  description = "12-digit AWS account ID trusted for AWS Workload Identity Federation."
  type        = string
  default     = "396610714890"
}

variable "aws_admin_role_name" {
  description = "AWS IAM role name for the EC2 admin API instance."
  type        = string
  default     = "theunending-admin"
}

variable "aws_publish_role_name" {
  description = "AWS IAM role name for the ECS Fargate publish task."
  type        = string
  default     = "theunending-publish-task"
}

variable "modal_workspace_id" {
  description = "Modal workspace ID allowed to federate via https://oidc.modal.com."
  type        = string
  default     = "ac-CUGZoMZ8GV9XJHWy1qggIn"
}

variable "pool_id" {
  description = "Workload Identity Pool ID in GCP."
  type        = string
  default     = "theunending-workloads"
}

variable "developer_emails" {
  description = "Optional Google user emails granted Service Account Token Creator for local CLI testing."
  type        = list(string)
  default     = []
}
