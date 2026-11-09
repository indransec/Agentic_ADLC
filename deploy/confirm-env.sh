#!/usr/bin/env bash
# Typed confirmation before destroying data (spec: reset and full rollback edge cases).
# Usage: deploy/confirm-env.sh "<what will happen>"
set -euo pipefail
env_name="${ADLC_ENV:-}"
if [[ -z "$env_name" ]]; then
  echo "ADLC_ENV is not set; refusing to continue" >&2
  exit 1
fi
echo "${1:-This will wipe ALL data} in ADLC_ENV=${env_name}."
read -r -p "Type the environment name to confirm: " answer
if [[ "$answer" != "$env_name" ]]; then
  echo "Confirmation did not match; nothing changed." >&2
  exit 1
fi
