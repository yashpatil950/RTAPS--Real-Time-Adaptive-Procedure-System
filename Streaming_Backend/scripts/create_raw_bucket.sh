#!/usr/bin/env bash
# Create (idempotently) the private, encrypted S3 bucket used by the RTAPS
# backend to archive raw eye-tracking data.
#
# Usage:
#   aws login                       # re-authenticate first (session was expired)
#   ./create_raw_bucket.sh [BUCKET_NAME]
#
# BUCKET_NAME defaults to "rtaps-raw-eye-data". S3 bucket names are GLOBALLY
# unique, so if that is taken pass your own, e.g.:
#   ./create_raw_bucket.sh rtaps-raw-eye-data-<your-suffix>
#
# After it succeeds, point the backend at the bucket:
#   export RAW_DATA_S3_BUCKET=<bucket-name>
#   export AWS_REGION=us-east-1
# and restart the backend.
set -euo pipefail

BUCKET="${1:-rtaps-raw-eye-data}"
REGION="${AWS_REGION:-us-east-1}"

echo "Creating s3://${BUCKET} in ${REGION} ..."
if aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
  echo "Bucket already exists; continuing to apply settings."
elif [ "${REGION}" = "us-east-1" ]; then
  aws s3api create-bucket --bucket "${BUCKET}" --region "${REGION}"
else
  aws s3api create-bucket --bucket "${BUCKET}" --region "${REGION}" \
    --create-bucket-configuration LocationConstraint="${REGION}"
fi

echo "Blocking all public access ..."
aws s3api put-public-access-block --bucket "${BUCKET}" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "Enabling default encryption (SSE-S3) ..."
aws s3api put-bucket-encryption --bucket "${BUCKET}" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

echo
echo "Done. Now set on the backend:"
echo "  export RAW_DATA_S3_BUCKET=${BUCKET}"
echo "  export AWS_REGION=${REGION}"
echo "and restart the streaming backend."
