#!/usr/bin/env bash
set -euo pipefail

required_vars=(
  MODEL_ID
  R2_ACCOUNT_ID
  R2_BUCKET
  R2_ACCESS_KEY_ID
  R2_SECRET_ACCESS_KEY
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required env var: ${var_name}" >&2
    exit 1
  fi
done

cd /app
python scripts/bootstrap_model.py
exec python scripts/start_server.py

