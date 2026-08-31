#!/usr/bin/env bash
# Point a Route 53 A record at the current edge public IP. UPSERT only that name.
set -euo pipefail
: "${HOSTED_ZONE_ID:?set HOSTED_ZONE_ID}" "${RECORD_NAME:?set RECORD_NAME (FQDN)}"
CLUSTER="${CLUSTER:-merchantos-staging}"
REGION="${AWS_REGION:-us-east-1}"
TTL="${TTL:-60}"
CONFIRM="${CONFIRM:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IP="$("$ROOT/scripts/edge-public-ip.sh")"
NAME="${RECORD_NAME%.}."
CHANGE="$(cat <<EOF
{
  "Comment": "MerchantOS edge A record for $CLUSTER",
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "$NAME",
      "Type": "A",
      "TTL": $TTL,
      "ResourceRecords": [{"Value": "$IP"}]
    }
  }]
}
EOF
)"
echo "zone=$HOSTED_ZONE_ID name=$NAME type=A ttl=$TTL value=$IP"
if [ "$CONFIRM" != "yes" ]; then
  echo "dry-run. re-run with CONFIRM=yes to apply." >&2
  exit 0
fi
aws route53 change-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID" \
  --change-batch "$CHANGE" --output text
echo "route53 upsert ok $NAME -> $IP"
