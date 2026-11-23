#!/bin/bash

set -euo pipefail

uv run modal secret create --force google-wif \
  GCP_WIF_PROVIDER="$( terraform -chdir=../terraform/gcp output -raw modal_wif_provider )" \
  GCP_SERVICE_ACCOUNT_EMAIL="$( terraform -chdir=../terraform/gcp output -raw modal_jobs_sa_email )"

uv run modal secret create --force google-machine \
  GOOGLE_SERVICE_ACCOUNT_EMAIL="$( terraform -chdir=../terraform/gcp output -raw admin_api_sa_email )"
