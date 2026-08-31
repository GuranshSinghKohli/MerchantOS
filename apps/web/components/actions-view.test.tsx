import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionsView } from "./actions-view";

vi.mock("@/lib/use-session-store", () => ({
  useSessionStore: () => ({
    isLoading: false,
    isError: false,
    data: { store_id: "s", shop_domain: "acme.myshopify.com" },
  }),
}));

vi.mock("@/lib/actions", async () => {
  const actual = await vi.importActual<typeof import("@/lib/actions")>("@/lib/actions");
  return {
    ...actual,
    fetchActions: vi.fn(),
    fetchPendingApprovals: vi.fn(),
    approveAction: vi.fn(),
    rejectAction: vi.fn(),
  };
});

import { approveAction, fetchActions, rejectAction } from "@/lib/actions";

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

const proposed = {
  action_id: "a1",
  status: "PROPOSED",
  action_type: "update_product_title",
  risk_level: "MEDIUM",
  title: "Update product title to “New Mug”",
  rationale: "Clearer merchandising title",
  resource: { id: "p1", gid: "gid://shopify/Product/9" },
  before_state: { title: "Old Mug" },
  after_state: { title: "New Mug" },
  evidence: [{ source_tool: "get_product_performance", fact_id: "ev_1" }],
  source_recommendation_id: "rec_1",
  expires_at: "2026-08-27T00:00:00+00:00",
  created_at: "2026-08-26T00:00:00+00:00",
  approval_status: null,
  error_code: null,
  error_message: null,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("actions view", () => {
  it("shows before and after and explicit approve or reject", async () => {
    vi.mocked(fetchActions).mockResolvedValue({ actions: [proposed] });
    vi.mocked(approveAction).mockResolvedValue({ ...proposed, status: "QUEUED" });
    render(wrap(<ActionsView />));
    expect(await screen.findByText("What will change?")).toBeTruthy();
    expect(screen.getByText("Old Mug")).toBeTruthy();
    expect(screen.getByText("New Mug")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approve Change" }));
    await waitFor(() => expect(approveAction).toHaveBeenCalledWith("a1"));
  });

  it("rejects from the same inspection card", async () => {
    vi.mocked(fetchActions).mockResolvedValue({ actions: [proposed] });
    vi.mocked(rejectAction).mockResolvedValue({ ...proposed, status: "REJECTED" });
    render(wrap(<ActionsView />));
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    await waitFor(() => expect(rejectAction).toHaveBeenCalledWith("a1"));
  });

  it("shows failed and expired states without approve", async () => {
    vi.mocked(fetchActions).mockResolvedValue({
      actions: [
        { ...proposed, action_id: "f1", status: "FAILED", error_message: "verification failed" },
        { ...proposed, action_id: "e1", status: "EXPIRED", title: "Expired title change" },
      ],
    });
    render(wrap(<ActionsView />));
    expect(await screen.findByText("verification failed")).toBeTruthy();
    expect(screen.getByText("Expired")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve Change" })).toBeNull();
  });
});
