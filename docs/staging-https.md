# Staging HTTPS runbook (ADR 0025)

**Architecture:** [ADR 0025](adr/0025-portfolio-cost-envelope.md). No Cloudflare. No ALB. No NAT Gateway. No ElastiCache.

```
Route 53 A record (stable hostname)
  → current edge task public IPv4 (changes on replace)
  → Caddy :80/:443 (Let's Encrypt)
  → API :8000 and web :3000 on localhost
```

Target cost remains **~$33–40/month** for one always-on environment ([aws-cost.md](aws-cost.md)). A Route 53 hosted zone adds about **$0.50/month**. Domain registration is yearly, not an ALB.

Shopify OAuth is valid only on **HTTPS** at this hostname. HTTP on the raw task IP is a temporary UI check, not an install URL.

## Task-IP replacement limitation

Fargate assigns a **new public IPv4** when the edge task is replaced. That includes:

- `terraform apply` that changes the edge task definition
- `aws ecs update-service --force-new-deployment`
- image deploys via `scripts/ecs-deploy.sh`
- the task crashing or failing health checks
- capacity replacement

**Do not click “update ip” on duckdns.org from your laptop.** That writes *your home address* and breaks Let’s Encrypt. Close any DuckDNS desktop client.

The Caddy container updates DuckDNS from the **task’s own public IP** before it asks Let’s Encrypt (`DUCKDNS_TOKEN` in Secrets Manager). After a recycle, wait for `duckdns_update_result=OK` in the Caddy log, then smoke HTTPS.

If you still manage DNS by hand:

Route 53 does **not** follow that IP. After every replace you must:

1. Read the new IP (`scripts/edge-public-ip.sh`)
2. UPSERT the same **A** record
3. Confirm Let's Encrypt still serves the hostname
4. Leave Shopify URLs **unchanged** unless the **hostname** itself changed

Do not point Shopify at an IP. Do not create a new app URL per deploy.

## First-time staging HTTPS

1. Host the name in **Route 53** (register there to use AWS credits, or create a hosted zone and set nameservers).
2. Set Terraform (`infra/terraform/envs/staging/terraform.tfvars`, not committed):

   ```hcl
   domain_name     = "staging.example.com"
   public_base_url = "https://staging.example.com"
   ```

   `public_base_url` must be the `https://` hostname. An `http://` IP leaves OAuth on HTTP.

3. Apply, then immediately run the replace procedure below (apply recycles the task).
4. Put `SHOPIFY_API_KEY` / `SHOPIFY_API_SECRET` in Secrets Manager `merchantos-staging/app` (Terraform ignores later `secret_string` drift).
5. After `/health` and `/ready` succeed on HTTPS, set Shopify Dev Dashboard and `shopify.app.toml` to that hostname once.

## Replace procedure (every edge recycle)

Cluster default: `merchantos-staging`. Region default: `us-east-1`.

### 1. Detect the current ECS public IP

```bash
CLUSTER=merchantos-staging ./scripts/edge-public-ip.sh
```

Wait until the edge service has `runningCount = 1` if this fails.

### 2. Update the DNS A record

```bash
export HOSTED_ZONE_ID=Zxxxxxxxxxxxx
export RECORD_NAME=staging.example.com
CLUSTER=merchantos-staging ./scripts/route53-upsert-edge-a.sh
# review the printed IP, then:
CONFIRM=yes CLUSTER=merchantos-staging ./scripts/route53-upsert-edge-a.sh
```

TTL is 60 seconds. Confirm:

```bash
dig +short staging.example.com
```

It must equal `./scripts/edge-public-ip.sh`.

### 3. Renew / validate HTTPS

Caddy requests and renews Let's Encrypt when `domain_name` is set and port 80 is reachable on the hostname. After the A record matches:

```bash
curl -fsS --max-time 30 "https://staging.example.com/health"
```

If TLS fails, wait two minutes (propagation + issuance), then:

```bash
aws logs tail /merchantos/merchantos-staging/edge --since 15m --format short
```

Look for Caddy certificate errors. Do not switch to HTTP for OAuth.

### 4. Shopify URLs (hostname change only)

| Situation | Shopify Dev Dashboard + `shopify.app.toml` |
|-----------|--------------------------------------------|
| Task IP changed, same hostname | **Do nothing** |
| Hostname changed (`staging.` → `app.`) | Update App URL and redirect, then reinstall |

Stable values:

- App URL: `https://staging.example.com`
- Redirect: `https://staging.example.com/api/v1/auth/shopify/callback`

Force a new edge deployment after editing Secrets Manager so tasks load new keys. Then repeat steps 1–3 (new IP).

### 5. Verify `/health` and `/ready`

```bash
./scripts/smoke.sh "https://staging.example.com"
```

Expect `smoke ok` (`"status":"ok"` and `"postgres":true`). Redis is `"skipped"` on AWS.

### 6. Verify Shopify OAuth after replacement

Same hostname, after DNS + HTTPS are good:

1. Open `https://staging.example.com/install`
2. Enter `{store}.myshopify.com` on a **development** store
3. Approve scopes
4. Land on `/install?installed=1` with a session cookie (Secure)
5. Overview loads (empty commerce data is fine)

If the callback 4xx/5xx: confirm `public_base_url` is `https://staging.example.com`, the secret has non-empty Shopify keys, and the Dev Dashboard redirect matches exactly.

## Later: ALB (not now)

Do not add an ALB without a new ADR and a cost update (~+$16–22/month). The seam that stays:

- Caddy still path-routes `/api/*`, `/health`, `/ready*` → API and the rest → web
- `public_base_url` remains the public hostname
- Route 53 would become an **alias** to the ALB; the A-to-task-IP step goes away
- Edge security group would accept 80 only from the ALB

Until then, the A-record update after every replace is mandatory.
