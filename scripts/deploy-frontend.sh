#!/bin/bash
# deploy-frontend.sh — Build and deploy frontend to S3 + invalidate CloudFront
# Usage: ./scripts/deploy-frontend.sh
#
# Required env vars (or set in .env):
#   FRONTEND_S3_BUCKET  — S3 bucket for frontend assets
#   CF_DISTRIBUTION_ID  — CloudFront distribution ID
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_DIR/frontend"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

S3_BUCKET="${FRONTEND_S3_BUCKET:?Set FRONTEND_S3_BUCKET env var}"
CF_DISTRIBUTION="${CF_DISTRIBUTION_ID:?Set CF_DISTRIBUTION_ID env var}"

echo "📦 Building frontend..."
cd "$FRONTEND_DIR"
npm run build

echo ""
echo "☁️  Uploading to S3..."
# Additive sync (no --delete) — leaves files outside dist/ intact, e.g.
# auth-related files dropped in by a private overlay.
aws s3 sync dist/ "s3://$S3_BUCKET/"

echo ""
echo "🔄 Invalidating CloudFront cache..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id "$CF_DISTRIBUTION" \
  --paths "/*" \
  --output text --query "Invalidation.Id")
echo "   Invalidation: $INVALIDATION_ID"

echo ""
echo "✅ Frontend deployed. Changes live in ~30s."
