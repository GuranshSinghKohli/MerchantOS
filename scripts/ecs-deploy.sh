#!/usr/bin/env bash
set -euo pipefail
: "${CLUSTER:?}" "${TAG:?}" "${REGISTRY:?}" "${PREFIX:?}"
REGION="${AWS_REGION:-us-east-1}"

rewrite_images() {
  local family="$1"
  local service="$2"
  local tmp
  tmp="$(mktemp)"
  aws ecs describe-task-definition --task-definition "$family" --region "$REGION" \
    --query 'taskDefinition' >"$tmp"
  python3 - "$tmp" "$REGISTRY" "$PREFIX" "$TAG" <<'PY'
import json, sys
path, registry, prefix, tag = sys.argv[1:5]
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
for container in data["containerDefinitions"]:
    name = container["name"]
    if name in {"api", "worker", "web", "caddy"}:
        container["image"] = f"{registry}/{prefix}/{name}:{tag}"
json.dump(data, open(path, "w"))
PY
  aws ecs register-task-definition --region "$REGION" --cli-input-json "file://$tmp" >/dev/null
  aws ecs update-service --region "$REGION" --cluster "$CLUSTER" --service "$service" \
    --task-definition "$family" --force-new-deployment >/dev/null
  rm -f "$tmp"
}

rewrite_images "${PREFIX}-edge" edge
rewrite_images "${PREFIX}-worker" worker
aws ecs wait services-stable --region "$REGION" --cluster "$CLUSTER" --services edge worker
echo "ecs deploy ok $TAG"
