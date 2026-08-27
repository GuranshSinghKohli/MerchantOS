import { fetchJson } from "@/lib/analytics";

export type ActionRecord = {
  action_id: string;
  status: string;
  action_type: string;
  risk_level: string;
  title: string;
  rationale: string;
  resource: { id: string; gid: string };
  before_state: Record<string, unknown>;
  after_state: Record<string, unknown>;
  evidence: { source_tool?: string; fact_id?: string }[];
  source_recommendation_id: string | null;
  expires_at: string | null;
  created_at: string | null;
  approval_status: string | null;
  error_code: string | null;
  error_message: string | null;
};

export type ActionsResponse = {
  actions: ActionRecord[];
};

export function fetchActions(): Promise<ActionsResponse> {
  return fetchJson("/api/v1/actions");
}

export function fetchPendingApprovals(): Promise<ActionsResponse> {
  return fetchJson("/api/v1/approvals");
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (response.status === 401) {
    throw new Error("Sign in by installing MerchantOS on your Shopify store.");
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "We could not complete that request. Try again.");
  }
  return (await response.json()) as T;
}

export function approveAction(actionId: string): Promise<ActionRecord> {
  return postJson(`/api/v1/actions/${actionId}/approve`, { confirm: true });
}

export function rejectAction(actionId: string): Promise<ActionRecord> {
  return postJson(`/api/v1/actions/${actionId}/reject`, { confirm: true });
}

export function fieldLabel(key: string): string {
  if (key === "title") return "Product title";
  if (key === "description") return "Product description";
  if (key === "tags") return "Product tags";
  if (key === "status") return "Product status";
  return key;
}

export function displayValue(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (value == null || value === "") return "—";
  return String(value);
}

export function changedFields(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): string[] {
  return ["title", "description", "tags", "status"].filter(
    (key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]),
  );
}
