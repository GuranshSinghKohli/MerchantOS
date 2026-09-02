#!/bin/sh
# Update DuckDNS from this task's egress IP, then start Caddy.
# Empty ip= tells DuckDNS to use the request source address (the Fargate public IPv4).
# Never log the token.
set -eu

domain="${DUCKDNS_DOMAIN:-}"
token="${DUCKDNS_TOKEN:-}"

if [ -n "$token" ] && [ -n "$domain" ]; then
  echo "duckdns_update_start domain=${domain}"
  result="$(wget -qO- "https://www.duckdns.org/update?domains=${domain}&token=${token}&ip=&verbose=true" || true)"
  echo "duckdns_update_result=${result}"
  # Give public resolvers and Let's Encrypt a moment to see the new A record.
  sleep 25
else
  echo "duckdns_update_skipped"
fi

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
