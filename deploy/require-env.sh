#!/usr/bin/env bash
# Refuse unless ADLC_ENV is one of the given environments (feature 014: the demo reset and the
# resilience checks change or destroy data; they run in the demo environment only).
# Usage: deploy/require-env.sh demo [dev ...]
set -euo pipefail
env_name="${ADLC_ENV:-}"
for allowed in "$@"; do
  if [[ "$env_name" == "$allowed" ]]; then
    exit 0
  fi
done
echo "refused: ADLC_ENV is '${env_name}'; this runs only in: $*" >&2
exit 1
