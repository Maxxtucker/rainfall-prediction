#!/usr/bin/env bash
# Run from an authenticated Cloud Shell in your own, billing-enabled project.
# Creates a private project bucket, dedicated VM identity, and cluster network.
set -euo pipefail
source "$(dirname "$0")/_env.sh"
gcloud config set project "$PROJECT_ID"
gcloud services enable dataproc.googleapis.com compute.googleapis.com \
  storage.googleapis.com iam.googleapis.com --project "$PROJECT_ID"

if ! gcloud storage buckets describe "$GCS_ROOT" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "$GCS_ROOT" --project "$PROJECT_ID" \
    --location "$REGION" --uniform-bucket-level-access
fi
gcloud storage buckets update "$GCS_ROOT" --public-access-prevention

if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" \
  --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT_ID" \
    --display-name="Rainfall Spark cluster VM identity"
fi
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" --role="roles/dataproc.worker" \
  --condition=None --quiet >/dev/null
gcloud storage buckets add-iam-policy-binding "$GCS_ROOT" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" --role="roles/storage.objectAdmin" >/dev/null
RAINFALL_USER_EMAIL="$(gcloud config get-value account 2>/dev/null)"
gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT" \
  --project "$PROJECT_ID" --member="user:${RAINFALL_USER_EMAIL}" \
  --role="roles/iam.serviceAccountUser" --quiet >/dev/null

if ! gcloud compute networks describe "$NETWORK" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute networks create "$NETWORK" --project "$PROJECT_ID" --subnet-mode=custom
fi
if ! gcloud compute networks subnets describe "$SUBNET" --project "$PROJECT_ID" \
  --region "$REGION" >/dev/null 2>&1; then
  gcloud compute networks subnets create "$SUBNET" --project "$PROJECT_ID" \
    --region "$REGION" --network "$NETWORK" --range "$SUBNET_RANGE" \
    --enable-private-ip-google-access
else
  gcloud compute networks subnets update "$SUBNET" --project "$PROJECT_ID" \
    --region "$REGION" --enable-private-ip-google-access
fi
if ! gcloud compute firewall-rules describe "${NETWORK}-cluster-internal" \
  --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud compute firewall-rules create "${NETWORK}-cluster-internal" \
    --project "$PROJECT_ID" --network "$NETWORK" --direction=INGRESS \
    --action=ALLOW --rules=tcp:0-65535,udp:0-65535,icmp \
    --source-ranges "$SUBNET_RANGE" --target-tags=rainfall-dataproc
fi
echo "Setup complete. Upload data before creating the billed Spark cluster."

