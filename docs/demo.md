# MerchantOS demo (5–10 minutes)

**[90-second demo video](https://guranshsinghkohli.github.io/MerchantOS/demo.html)**

Staging hostname: `https://merchantos.duckdns.org`  
Local: `http://localhost:3000` after `make api`, `make worker`, `make web`.

Do not weaken OAuth, approval, or tenant isolation for the demo.

## Happy path (store connected + data imported)

1. **Install** — Open `/install`. Enter `{store}.myshopify.com`. Complete Shopify OAuth. Tokens never appear in the browser.
2. **Overview** — Confirm **Connected**. If import has not run, use **Import store data** and wait for the worker. Do not treat zeros as real revenue.
3. **Analytics** — Date range, revenue / orders / AOV / customers. These numbers come from the Postgres projection, not from the model.
4. **Ask MerchantOS** — Suggested question: “How is my store doing?” or the flagship “How can I increase profit this month without increasing ad spend?”
5. **Answer** — Concise summary, confidence, “looked at Revenue / Inventory / Customers”.
6. **Evidence** — Open **Supporting evidence**. Facts are tool outputs (`revenue=80.00`), not chain-of-thought.
7. **Recommendation** — Advisory text only. No Approve button on this screen.
8. **Approvals** — If a product change was proposed from the Actions API, show current vs proposed, risk, and why.
9. **Approve Change** — Explicit button. High-impact changes require the checkbox.
10. **Shopify** — Worker runs the typed mutator. Status: Queued → Updating store → Done.
11. **Verification** — Done means the re-read matched. Failed shows a merchant-safe reason.
12. **Audit** — Action history on **Actions**. Settings never show tokens.

## Fallback (empty development store)

Staging often has **Connected** + **Not imported** or zero paid orders. That is expected.

1. Show `/install` success and Overview **Connected**.
2. Show the empty-store card: “Import your Shopify store to see insights.” Explain that MerchantOS will not invent revenue.
3. Click **Import store data** if the worker and Shopify credentials are live. If Shopify catalog is empty, the import completes and Overview still says **No orders in this date range**.
4. Open **Ask MerchantOS** and ask “How is my store doing?” The graph should report insufficient evidence rather than fabricate KPIs.
5. Walk **Approvals** with a locally proposed title change (session + `POST /api/v1/actions`) if you need the before/after UI. Still require **Approve Change**.

Never paste fake KPI screenshots as if they were this store.

## What to say

- “The LLM cannot approve or mutate.”
- “Tenant comes from the session cookie, not from the question.”
- “CI AgentBench is FakeLLM; live models are operator-gated.”
- “Staging cost is about $33–40/month; production apply is gated.”
