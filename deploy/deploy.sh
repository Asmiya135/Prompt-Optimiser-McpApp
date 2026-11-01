#!/usr/bin/env bash
# Deploy the prompt optimizer MCP server to Cloud Run, staying inside the free tier.
#
# Before running: gcloud auth login, Gemini Enterprise app created (README step 2), Web OAuth client (step 3).
# Usage:
#   PROJECT_ID=my-project OAUTH_CLIENT_ID=123-abc.apps.googleusercontent.com ./deploy/deploy.sh
# Optional: REGION (default asia-south1), SERVICE (default prompt-optimizer),
#           ALLOWED_EMAIL_DOMAINS, ALLOWED_EMAILS, GEMINI_API_KEY (exact token counts; not needed for the demo)
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${OAUTH_CLIENT_ID:?Set OAUTH_CLIENT_ID (README step 3)}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-prompt-optimizer}"
RUN_SA_NAME="prompt-optimizer-run"
RUN_SA="${RUN_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

cd "$(dirname "$0")/.."
gcloud config set project "$PROJECT_ID"

echo "== 1. Enable APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  discoveryengine.googleapis.com

echo "== 2. Runtime service account with no roles (least privilege: the server calls no Google APIs)"
gcloud iam service-accounts describe "$RUN_SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$RUN_SA_NAME" --display-name="Prompt optimizer (Cloud Run)"

# "^;^" tells gcloud to split on ";" (see `gcloud topic escaping`), so values may contain commas.
ENV_VARS="^;^AUTH_MODE=google;OAUTH_CLIENT_ID=${OAUTH_CLIENT_ID};TARGET_MODEL=gemini"
if [[ -n "${ALLOWED_EMAIL_DOMAINS:-}" ]]; then ENV_VARS="${ENV_VARS};ALLOWED_EMAIL_DOMAINS=${ALLOWED_EMAIL_DOMAINS}"; fi
if [[ -n "${ALLOWED_EMAILS:-}" ]]; then ENV_VARS="${ENV_VARS};ALLOWED_EMAILS=${ALLOWED_EMAILS}"; fi

SECRET_FLAGS=()
if [[ -n "${GEMINI_API_KEY:-}" ]]; then
  echo "== 2b. Store the Gemini key in Secret Manager"
  gcloud services enable secretmanager.googleapis.com
  if gcloud secrets describe gemini-api-key >/dev/null 2>&1; then
    printf %s "$GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
  else
    printf %s "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
  fi
  gcloud secrets add-iam-policy-binding gemini-api-key \
    --member="serviceAccount:${RUN_SA}" --role=roles/secretmanager.secretAccessor >/dev/null
  SECRET_FLAGS=(--set-secrets=GEMINI_API_KEY=gemini-api-key:latest)
fi

echo "== 3. Build and deploy (request-based billing, scales to zero, at most 2 instances)"
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --service-account "$RUN_SA" \
  --no-allow-unauthenticated \
  --cpu-throttling \
  --min-instances 0 \
  --max-instances 2 \
  --cpu 1 --memory 512Mi \
  --concurrency 40 --timeout 60 \
  --set-env-vars "$ENV_VARS" \
  ${SECRET_FLAGS[@]+"${SECRET_FLAGS[@]}"}

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
gcloud run services update "$SERVICE" --region "$REGION" --update-env-vars "PUBLIC_URL=${URL}" >/dev/null

echo "== 4. Let the Gemini Enterprise service agent call the service (layer 1 auth)"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
AGENT="service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com"
if ! gcloud run services add-iam-policy-binding "$SERVICE" --region "$REGION" \
      --member="serviceAccount:${AGENT}" --role=roles/run.invoker >/dev/null; then
  echo "!! Could not grant run.invoker to ${AGENT}."
  echo "   The service agent appears once Gemini Enterprise is set up in this project."
  echo "   Create the Gemini Enterprise app (README step 2), then re-run this script."
  exit 1
fi

echo
echo "Done. MCP Server URL for Gemini Enterprise:  ${URL}/mcp"
