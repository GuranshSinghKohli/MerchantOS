import { fetchJson } from "@/lib/analytics";

export type SyncStatus = {
  store_sync_status: string;
  sync_error: string | null;
};

export function fetchSyncStatus(): Promise<SyncStatus> {
  return fetchJson("/api/v1/store/sync");
}

export async function startStoreImport(): Promise<void> {
  const response = await fetch("/api/v1/store/sync", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "initial" }),
  });
  if (response.status === 401) {
    throw new Error("Sign in by installing MerchantOS on your Shopify store.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? "We could not start the store import. Try again.");
  }
}
