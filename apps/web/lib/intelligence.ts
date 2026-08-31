import { fetchJson } from "@/lib/analytics";

export type IntelligenceEvidence = {
  id: string;
  source: string;
  fact: string;
};

export type IntelligenceFinding = {
  id: string;
  title: string;
  description: string;
  evidence_ids: string[];
  limitations?: string[];
};

export type IntelligenceInsight = {
  id: string;
  title: string;
  description: string;
  kind: string;
  evidence_ids: string[];
};

export type IntelligenceRecommendation = {
  id: string;
  title: string;
  recommendation: string;
  rationale: string;
  evidence_ids: string[];
  expected_objective: string;
  priority: string;
  confidence: string;
  limitations: string[];
};

export type IntelligenceResult = {
  executive_summary: string;
  findings: IntelligenceFinding[];
  insights: IntelligenceInsight[];
  recommendations: IntelligenceRecommendation[];
  evidence: IntelligenceEvidence[];
  contradictions: { id: string; metric: string; left_fact: string; right_fact: string }[];
  limitations: string[];
  confidence: string;
  selected_agents: string[];
};

export type IntelligenceRun = {
  run_id: string;
  status: string;
  question: string;
  result: IntelligenceResult | null;
  error_message: string | null;
  created_at: string | null;
};

export async function startIntelligence(question: string): Promise<IntelligenceRun> {
  const response = await fetch("/api/v1/intelligence/query", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (response.status === 401) {
    throw new Error("Sign in by installing MerchantOS on your Shopify store.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? "We could not start that question. Try again.");
  }
  return (await response.json()) as IntelligenceRun;
}

export function fetchIntelligence(runId: string): Promise<IntelligenceRun> {
  return fetchJson(`/api/v1/intelligence/${runId}`);
}

export function listIntelligence(): Promise<{ runs: IntelligenceRun[] }> {
  return fetchJson("/api/v1/intelligence");
}

export function evidenceFor(ids: string[], evidence: IntelligenceEvidence[]): IntelligenceEvidence[] {
  const known = new Map(evidence.map((item) => [item.id, item]));
  return ids.map((id) => known.get(id)).filter((item): item is IntelligenceEvidence => Boolean(item));
}
