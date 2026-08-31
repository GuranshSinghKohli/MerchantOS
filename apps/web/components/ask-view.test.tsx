import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AskView } from "./ask-view";

vi.mock("@/lib/use-session-store", () => ({
  useSessionStore: () => ({
    isLoading: false,
    isError: false,
    data: { store_id: "s", shop_domain: "acme.myshopify.com" },
  }),
}));

vi.mock("@/lib/intelligence", async () => {
  const actual = await vi.importActual<typeof import("@/lib/intelligence")>("@/lib/intelligence");
  return {
    ...actual,
    listIntelligence: vi.fn(),
    startIntelligence: vi.fn(),
    fetchIntelligence: vi.fn(),
  };
});

import { fetchIntelligence, listIntelligence, startIntelligence } from "@/lib/intelligence";

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("ask view", () => {
  it("submits a question and shows evidence without graph internals", async () => {
    vi.mocked(listIntelligence).mockResolvedValue({ runs: [] });
    vi.mocked(startIntelligence).mockResolvedValue({
      run_id: "r1",
      status: "PENDING",
      question: "How is my store doing?",
      result: null,
      error_message: null,
      created_at: null,
    });
    vi.mocked(fetchIntelligence).mockResolvedValue({
      run_id: "r1",
      status: "COMPLETED",
      question: "How is my store doing?",
      error_message: null,
      created_at: null,
      result: {
        executive_summary: "Revenue is 80.00 in the latest window.",
        findings: [
          {
            id: "f1",
            title: "Revenue snapshot",
            description: "Revenue is 80.00 versus previous 40.00.",
            evidence_ids: ["ev_1"],
          },
        ],
        insights: [],
        recommendations: [
          {
            id: "rec1",
            title: "Review the latest signals",
            recommendation: "Investigate the metrics cited by the selected specialists.",
            rationale: "Evidence from store data supports a review.",
            evidence_ids: ["ev_1"],
            expected_objective: "Understand current performance",
            priority: "MEDIUM",
            confidence: "MEDIUM",
            limitations: ["Advisory only"],
          },
        ],
        evidence: [{ id: "ev_1", source: "get_revenue_metrics", fact: "revenue=80.00" }],
        contradictions: [],
        limitations: [],
        confidence: "MEDIUM",
        selected_agents: ["analytics"],
      },
    });
    render(wrap(<AskView />));
    fireEvent.click(await screen.findByRole("button", { name: "How is my store doing?" }));
    expect(await screen.findByText("Revenue is 80.00 in the latest window.")).toBeTruthy();
    fireEvent.click(screen.getAllByText("Supporting evidence")[0]);
    expect(screen.getAllByText("revenue=80.00").length).toBeGreaterThan(0);
    expect(screen.queryByText("AgentState")).toBeNull();
    expect(screen.queryByText("LangGraph")).toBeNull();
    await waitFor(() => expect(startIntelligence).toHaveBeenCalled());
  });
});
