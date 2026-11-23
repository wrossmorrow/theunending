# GCP Workload Identity Federation (Keyless Machine Auth)

This module provisions zero-permission GCP service accounts and Workload Identity Federation (WIF) providers so AWS (EC2 admin API + ECS Fargate publish tasks) and Modal jobs can mint Google-signed OIDC ID tokens without creating any service account JSON keys.

## What It Creates

- Enables `iam.googleapis.com`, `iamcredentials.googleapis.com`, and `sts.googleapis.com`.
- Three zero-permission service accounts:
  - `admin-api@<project>.iam.gserviceaccount.com` (EC2 admin API → Modal entrypoint)
  - `modal-jobs@<project>.iam.gserviceaccount.com` (Modal GPU jobs → Envoy gateway)
  - `publish-job@<project>.iam.gserviceaccount.com` (ECS Fargate publish tasks → Envoy gateway)
- One Workload Identity Pool (`theunending-workloads`) with two providers:
  - `aws-iam`: trusts AWS account `396610714890`, restricted to `assumed-role/theunending-admin/*` and `assumed-role/theunending-publish-task/*`.
  - `modal`: trusts OIDC issuer `https://oidc.modal.com` (audience `oidc.modal.com`), restricted to `modal:workspace_id:ac-CUGZoMZ8GV9XJHWy1qggIn:*`.
- `roles/iam.serviceAccountTokenCreator` bindings tying each workload identity to its service account.

## Option 1: Apply with Terraform

```bash
cd terraform/gcp
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars (verify gcp_project_id matches your OAuth project, e.g. thunending-oauth)

gcloud auth application-default login
terraform init
terraform apply
```

Capture the outputs:

```bash
terraform output
```

## Option 2: Equivalent `gcloud` Commands

If you prefer creating these resources directly with `gcloud`:

```bash
export GCP_PROJECT_ID="thunending-oauth"
export GCP_PROJECT_NUMBER="$(gcloud projects describe "${GCP_PROJECT_ID}" --format='value(projectNumber)')"
export AWS_ACCOUNT_ID="396610714890"
export MODAL_WORKSPACE_ID="ac-CUGZoMZ8GV9XJHWy1qggIn"
export POOL_ID="theunending-workloads"

gcloud services enable iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  --project="${GCP_PROJECT_ID}"

for SA in admin-api modal-jobs publish-job; do
  gcloud iam service-accounts create "${SA}" \
    --project="${GCP_PROJECT_ID}" \
    --display-name="The Unending ${SA}"
done

gcloud iam workload-identity-pools create "${POOL_ID}" \
  --project="${GCP_PROJECT_ID}" \
  --location="global" \
  --display-name="The Unending Workloads"

gcloud iam workload-identity-pools providers create-aws "aws-iam" \
  --project="${GCP_PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --account-id="${AWS_ACCOUNT_ID}" \
  --attribute-mapping="google.subject=assertion.arn,attribute.aws_account=assertion.account,attribute.aws_role=assertion.arn.extract('assumed-role/{role}/')" \
  --attribute-condition="assertion.account == '${AWS_ACCOUNT_ID}' && (assertion.arn.startsWith('arn:aws:sts::${AWS_ACCOUNT_ID}:assumed-role/theunending-admin/') || assertion.arn.startsWith('arn:aws:sts::${AWS_ACCOUNT_ID}:assumed-role/theunending-publish-task/'))"

gcloud iam workload-identity-pools providers create-oidc "modal" \
  --project="${GCP_PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --issuer-uri="https://oidc.modal.com" \
  --allowed-audiences="oidc.modal.com" \
  --attribute-mapping="google.subject=assertion.sub.extract('modal:workspace_id:{ws}:'),attribute.workspace_id=assertion.sub.extract('modal:workspace_id:{ws}:')" \
  --attribute-condition="assertion.sub.startsWith('modal:workspace_id:${MODAL_WORKSPACE_ID}:')"

POOL_PATH="projects/${GCP_PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}"

gcloud iam service-accounts add-iam-policy-binding \
  "admin-api@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${GCP_PROJECT_ID}" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --member="principalSet://iam.googleapis.com/${POOL_PATH}/attribute.aws_role/theunending-admin"

gcloud iam service-accounts add-iam-policy-binding \
  "publish-job@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${GCP_PROJECT_ID}" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --member="principalSet://iam.googleapis.com/${POOL_PATH}/attribute.aws_role/theunending-publish-task"

gcloud iam service-accounts add-iam-policy-binding \
  "modal-jobs@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${GCP_PROJECT_ID}" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --member="principalSet://iam.googleapis.com/${POOL_PATH}/attribute.workspace_id/${MODAL_WORKSPACE_ID}"
```

## Wiring Up AWS, Modal, and Envoy

1. **AWS Terraform (`terraform/`):** Set in `terraform.tfvars` and run `terraform apply`:
   - `gcp_aws_wif_provider = "<aws_wif_provider output>"`
   - `gcp_publish_sa_email = "<publish_job_sa_email output>"`
2. **Admin EC2 (`admin/deploy/.env`):** Set:
   - `GCP_WIF_PROVIDER=<aws_wif_provider output>`
   - `GCP_SERVICE_ACCOUNT_EMAIL=<admin_api_sa_email output>`
   - Optionally `MODAL_API_AUDIENCE=https://morrowwr--theunending-api-entrypoint.us-east.modal.run` (if you want a distinct audience from Envoy's `https://admin.theunending.ai`).
3. **Envoy (`admin/deploy/envoy.yaml`):** Replace:
   - `REPLACE_WITH_MODAL_JOBS_SA_EMAIL` with `<modal_jobs_sa_email output>`
   - `REPLACE_WITH_PUBLISH_JOB_SA_EMAIL` with `<publish_job_sa_email output>`
4. **Modal secrets:** Create two non-secret config secrets in Modal:
   ```bash
   # Used by Modal GPU jobs (evaluate, batch, embed) calling back into Envoy:
   modal secret create google-wif \
     GCP_WIF_PROVIDER="<modal_wif_provider output>" \
     GCP_SERVICE_ACCOUNT_EMAIL="<modal_jobs_sa_email output>"

   # Used by Modal API entrypoint (code/modal/api.py) verifying Admin API calls:
   modal secret create google-machine \
     GOOGLE_SERVICE_ACCOUNT_EMAIL="<admin_api_sa_email output>"
   # Optional if using a separate audience for Modal:
   #   MODAL_API_AUDIENCE="https://morrowwr--theunending-api-entrypoint.us-east.modal.run"
   ```
5. **Local CLI scripts (`code/modal/batch-api.sh`, `code/remote/finish-entrypoint.sh`):**
   Add your email to `developer_emails` in `terraform/gcp/terraform.tfvars`, log in with `gcloud auth login`, and export `GCP_SERVICE_ACCOUNT_EMAIL` before running the script.
