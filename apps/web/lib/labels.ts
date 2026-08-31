const AGENT_LABEL: Record<string, string> = {
  analytics: "Revenue",
  inventory: "Inventory",
  customer: "Customers",
  orchestrator: "Store overview",
};

const ACTION_STATUS: Record<string, string> = {
  PROPOSED: "Waiting for you",
  QUEUED: "Queued",
  EXECUTING: "Updating store",
  COMPLETED: "Done",
  FAILED: "Could not update",
  CONFLICT: "Store changed first",
  EXPIRED: "Expired",
  REJECTED: "Rejected",
  BLOCKED: "Not allowed",
};

const SYNC_STATUS: Record<string, string> = {
  not_started: "Not imported",
  pending: "Importing",
  running: "Importing",
  completed: "Up to date",
  failed: "Import failed",
  uninstalled: "Disconnected",
};

export function agentLabel(name: string): string {
  return AGENT_LABEL[name] ?? "Store data";
}

export function actionStatusLabel(status: string): string {
  return ACTION_STATUS[status] ?? status;
}

export function syncStatusLabel(status: string): string {
  return SYNC_STATUS[status] ?? status;
}

export function riskLabel(level: string): string {
  if (level === "HIGH" || level === "CRITICAL") return "High impact";
  if (level === "MEDIUM") return "Needs your review";
  return "Review";
}

export function confidenceLabel(value: string): string {
  if (value === "HIGH") return "High confidence";
  if (value === "LOW") return "Low confidence";
  return "Medium confidence";
}

export function neverSynced(status: string): boolean {
  return status === "not_started" || status === "uninstalled";
}

export function syncInFlight(status: string): boolean {
  return status === "pending" || status === "running";
}
