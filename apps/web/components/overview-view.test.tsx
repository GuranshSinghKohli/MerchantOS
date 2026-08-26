import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OverviewView } from "./overview-view";
import { EmptyBoard, ErrorBoard, LoadingBoard } from "./states";

vi.mock("@/lib/analytics", async () => {
  const actual = await vi.importActual<typeof import("@/lib/analytics")>("@/lib/analytics");
  return {
    ...actual,
    fetchOverview: vi.fn(),
    fetchSession: vi.fn(),
  };
});

import { fetchOverview, fetchSession } from "@/lib/analytics";

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("dashboard states", () => {
  it("renders a loading skeleton", () => {
    render(<LoadingBoard />);
    expect(screen.getByText("Loading analytics")).toBeTruthy();
  });

  it("renders an empty explanation", () => {
    render(<EmptyBoard title="No included orders in this range" body="Sync a store" />);
    expect(screen.getByText("No included orders in this range")).toBeTruthy();
  });

  it("renders a merchant-safe error", () => {
    render(<ErrorBoard message="Sign in by installing MerchantOS on your Shopify store." />);
    expect(screen.getByText("We could not load this view")).toBeTruthy();
    expect(screen.queryByText(/traceback/i)).toBeNull();
  });

  it("renders KPIs from a successful overview payload", async () => {
    vi.mocked(fetchSession).mockResolvedValue({
      store_id: "s",
      shop_domain: "acme.myshopify.com",
    });
    vi.mocked(fetchOverview).mockResolvedValue({
      request_id: "req",
      store: {
        store_id: "s",
        shop_domain: "acme.myshopify.com",
        timezone: "UTC",
        currency: "USD",
        installed: true,
        sync_status: "completed",
      },
      range: {
        current: { start_local: "2026-08-01", end_local_exclusive: "2026-08-27", timezone: "UTC" },
        previous: { start_local: "2026-07-06", end_local_exclusive: "2026-08-01" },
        compare: "previous_period",
      },
      kpis: {
        revenue: "100.00",
        orders: 2,
        aov: "50.00",
        customers: 1,
        new_customers: 1,
        returning_customers: 0,
        cancelled_orders: 0,
        growth_pct: { revenue: "10.00", orders: "0.00", customers: null, aov: "11.11" },
        previous: { revenue: "90.00", orders: 2, aov: "45.00", customers: 1 },
      },
      trends: { revenue: [{ date: "2026-08-20", revenue: "100.00", orders: 2 }], customers: [] },
      products: [
        {
          product_gid: "gid://shopify/Product/1",
          title: "Hero Mug",
          status: "ACTIVE",
          units_sold: 2,
          revenue: "100.00",
          available: 3,
        },
      ],
      inventory: {
        tracked_variants: 1,
        in_stock_variants: 1,
        out_of_stock_variants: 0,
        available_units: 3,
        on_hand_units: 4,
        utilization_pct: "75.00",
      },
      health: {
        score: 70,
        status: "watch",
        summary: "MerchantOS health indicator is 70/100 (watch).",
        label: "MerchantOS health indicator",
        components: [],
      },
      opportunities: [],
    });
    render(wrap(<OverviewView />));
    expect(await screen.findByText("acme.myshopify.com")).toBeTruthy();
    expect(screen.getByText("Hero Mug")).toBeTruthy();
    expect(screen.getAllByText("Revenue").length).toBeGreaterThan(0);
  });
});
