#!/usr/bin/env bash
# Print the running edge task public IPv4. That address changes on every replace.
set -euo pipefail
CLUSTER="${CLUSTER:-merchantos-staging}"
REGION="${AWS_REGION:-us-east-1}"
TASK="$(aws ecs list-tasks --region "$REGION" --cluster "$CLUSTER" \
  --service-name edge --desired-status RUNNING --query 'taskArns[0]' --output text)"
if [ -z "$TASK" ] || [ "$TASK" = "None" ]; then
  echo "no running edge task on $CLUSTER" >&2
  exit 1
fi
ENI="$(aws ecs describe-tasks --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK" \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text)"
IP="$(aws ec2 describe-network-interfaces --region "$REGION" --network-interface-ids "$ENI" \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text)"
if [ -z "$IP" ] || [ "$IP" = "None" ]; then
  echo "edge task $TASK has no public IP yet" >&2
  exit 1
fi
echo "$IP"
