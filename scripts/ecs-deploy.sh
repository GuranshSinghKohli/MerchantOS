#!/usr/bin/env bash
set -euo pipefail
: "${CLUSTER:?}" "${TAG:?}" "${REGISTRY:?}" "${PREFIX:?}"
REGION="${AWS_REGION:-us-east-1}"

rewrite_family() {
  local family="$1"
  local service="$2"
  local image="$REGISTRY/$PREFIX/$service:$TAG"
  local tmp
  tmp="$(mktemp)"
  aws ecs describe-task-definition --task-definition "$family" --region "$REGION" \
    --query 'taskDefinition' >"$tmp"
  python3 - "$tmp" "$image" <<'PY'
import json, sys
path, image = sys.argv[1], sys.argv[2]
data = json.load(open(path))
for key in (
    "taskDefinitionArn",
    "revision",
    "status",
    "requiresAttributes",
    "compatibilities",
    "registeredAt",
    "registeredBy",
):
    data.pop(key, None)
data["containerDefinitions"][0]["image"] = image
json.dump(data, open(path, "w"))
PY
  aws ecs register-task-definition --region "$REGION" --cli-input-json "file://$tmp" >/dev/null
  aws ecs update-service --region "$REGION" --cluster "$CLUSTER" --service "$service" \
    --task-definition "$family" --force-new-deployment >/dev/null
  rm -f "$tmp"
}

rewrite_family "${PREFIX}-api" api
rewrite_family "${PREFIX}-worker" worker
rewrite_family "${PREFIX}-web" web
aws ecs wait services-stable --region "$REGION" --cluster "$CLUSTER" --services api web worker
echo "ecs deploy ok $TAG"
