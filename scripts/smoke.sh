#!/usr/bin/env bash
set -euo pipefail
BASE="${1:?usage: scripts/smoke.sh https://host}"
curl -fsS "$BASE/health" | grep -q '"status":"ok"'
curl -fsS "$BASE/ready" | grep -q '"postgres":true'
echo "smoke ok $BASE"
