output "gcp_project_number" {
  description = "Numeric GCP project number used in WIF provider resource names."
  value       = data.google_project.current.number
}

output "aws_wif_provider" {
  description = "Value for GCP_WIF_PROVIDER on AWS EC2 (admin API) and ECS Fargate (publish task)."
  value       = local.aws_wif_provider_name
}

output "modal_wif_provider" {
  description = "Value for GCP_WIF_PROVIDER in the Modal 'google-wif' secret."
  value       = local.modal_wif_provider_name
}

output "admin_api_sa_email" {
  description = "Service account email used by Admin API -> Modal (set in EC2 .env and Modal 'google-machine' secret)."
  value       = google_service_account.admin_api.email
}

output "modal_jobs_sa_email" {
  description = "Service account email used by Modal jobs -> Envoy (set in Modal 'google-wif' secret and envoy.yaml)."
  value       = google_service_account.modal_jobs.email
}

output "publish_job_sa_email" {
  description = "Service account email used by Fargate publish tasks -> Envoy (set in AWS tfvars and envoy.yaml)."
  value       = google_service_account.publish_job.email
}
