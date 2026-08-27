#!/usr/bin/env bash
set -euo pipefail
: "${CLUSTER:?}" "${SUBNETS:?}" "${SECURITY_GROUP:?}" "${MIGRATE_TASK:?}"
REGION="${AWS_REGION:-us-east-1}"
task_arn="$(aws ecs run-task --region "$REGION" --cluster "$CLUSTER" --task-definition "$MIGRATE_TASK" \
  --launch-type FARGATE --count 1 \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
  --query 'tasks[0].taskArn' --output text)"
aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$task_arn"
exit_code="$(aws ecs describe-tasks --region "$REGION" --cluster "$CLUSTER" --tasks "$task_arn" \
  --query 'tasks[0].containers[0].exitCode' --output text)"
test "$exit_code" = "0"
echo "migrate ok"
