#!/usr/bin/env bash
# Live isolation check (feature 009, SC-007): platform services cannot reach the pilot network and
# the pilot cannot reach the platform's database, API or knowledge server. Run with the stack up.
set -u
COMPOSE=(docker compose -f "$(dirname "$0")/compose.yaml" --env-file "$(dirname "$0")/../.env")
fail=0

probe() {  # service host port -> prints "open" or "closed"
  "${COMPOSE[@]}" exec -T "$1" python -c "
import socket, sys
s = socket.socket(); s.settimeout(2)
try:
    s.connect(('$2', $3)); print('open')
except OSError:
    print('closed')
" 2>/dev/null | tr -d '\r'
}

expect() {  # expected service host port
  local got
  got=$(probe "$2" "$3" "$4")
  if [[ "$got" == "$1" ]]; then echo "ok    $2 -> $3:$4 $got"; else echo "FAIL  $2 -> $3:$4 $got (expected $1)"; fail=1; fi
}

for svc in api orchestrator knowledge; do expect closed "$svc" pilot-prodsim 8100; done
for target in "postgres 5432" "api 8000" "knowledge 8020"; do
  # shellcheck disable=SC2086
  expect closed pilot-prodsim $target
done
expect open pilot-traffic pilot-prodsim 8100   # inside the pilot network
exit $fail
