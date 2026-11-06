#!/usr/bin/env bash
# Usage: LLM_MODEL=provider:model ./infra/deploy.sh
# Needs Secret Manager secrets named llm-api-key, langfuse-public and langfuse-secret.
# Set LLM_KEY_NAME to your provider's variable, for example ANTHROPIC_API_KEY.
set -euo pipefail
PROJECT_ID="$(gcloud config get-value project)"
: "${LLM_KEY_NAME:=OPENAI_API_KEY}"
gcloud run deploy datapilot --source . --region europe-west1 \
  --service-account "datapilot-api@${PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars "LLM_MODEL=${LLM_MODEL}" \
  --set-secrets "${LLM_KEY_NAME}=llm-api-key:latest,LANGFUSE_PUBLIC_KEY=langfuse-public:latest,LANGFUSE_SECRET_KEY=langfuse-secret:latest" \
  --allow-unauthenticated --memory 1Gi --max-instances 1
