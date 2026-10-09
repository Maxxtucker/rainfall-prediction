#!/usr/bin/env bash
# This command starts billed VMs. Run only after raw data are safely in GCS.
set -euo pipefail
source "$(dirname "$0")/_env.sh"
gcloud dataproc clusters create "$CLUSTER" \
  --project "$PROJECT_ID" --region "$REGION" \
  --subnet "$SUBNET" --no-address --tags=rainfall-dataproc \
  --service-account "$SERVICE_ACCOUNT" --scopes=cloud-platform \
  --image-version "$IMAGE_VERSION" \
  --master-machine-type "$MASTER_MACHINE" \
  --num-workers "$NUM_WORKERS" --worker-machine-type "$WORKER_MACHINE" \
  --master-boot-disk-type=pd-balanced --worker-boot-disk-type=pd-balanced \
  --master-boot-disk-size "$BOOT_DISK_GB" --worker-boot-disk-size "$BOOT_DISK_GB" \
  --bucket "$BUCKET" --temp-bucket "$BUCKET" \
  --enable-component-gateway \
  --properties="spark:spark.sql.session.timeZone=Asia/Singapore,spark:spark.sql.shuffle.partitions=128,spark:spark.sql.adaptive.enabled=true" \
  --delete-max-idle "$DELETE_MAX_IDLE" --delete-max-age "$DELETE_MAX_AGE" \
  --labels="project=singapore-rainfall,run=${RUN_ID}"

mkdir -p "${RAINFALL_ROOT}/outputs/environment"
gcloud dataproc clusters describe "$CLUSTER" --project "$PROJECT_ID" \
  --region "$REGION" --format=json >"${RAINFALL_ROOT}/outputs/environment/cluster.json"
gcloud version --format=json >"${RAINFALL_ROOT}/outputs/environment/gcloud.json"
gcloud storage cp "${RAINFALL_ROOT}/outputs/environment/cluster.json" \
  "${RAINFALL_ROOT}/outputs/environment/gcloud.json" "${OUTPUT_ROOT}/environment/"
echo "Cluster ready. Submit jobs now; idle deletion is ${DELETE_MAX_IDLE}, maximum age is ${DELETE_MAX_AGE}."

