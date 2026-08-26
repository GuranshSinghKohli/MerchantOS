"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { DateRangeBar } from "@/components/date-range-bar";
import { OverviewView } from "@/components/overview-view";
import { EmptyBoard, ErrorBoard, LoadingBoard } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendChart } from "@/components/trend-chart";
import {
  type AnalyticsQuery,
  type CompareMode,
  type DatePreset,
  type OverviewResponse,
  analyticsSearch,
  fetchCustomers,
  fetchJson,
  fetchOverview,
  formatMoney,
  isQueryReady,
} from "@/lib/analytics";
import { useSessionStore } from "@/lib/use-session-store";

function CustomRangePrompt({ title }: { title: string }) {
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">{title}</h1>
      <DateRangeBar />
      <EmptyBoard title="Choose a custom range" body="Pick a start and end date. Both days are inclusive." />
    </div>
  );
}

function useAnalyticsQuery(): AnalyticsQuery {
  const params = useSearchParams();
  return {
    preset: (params.get("preset") as DatePreset) || "last_30",
    compare: (params.get("compare") as CompareMode) || "previous_period",
    from: params.get("from") ?? undefined,
    to: params.get("to") ?? undefined,
  };
}

export function AnalyticsPageView() {
  return <OverviewView />;
}

export function InventoryView() {
  const query = useAnalyticsQuery();
  const session = useSessionStore();
  const request = useQuery({
    queryKey: ["analytics-inventory", session.data?.store_id, query],
    queryFn: () => fetchJson<Pick<OverviewResponse, "inventory" | "products" | "store">>(`/api/v1/analytics/inventory?${analyticsSearch(query)}`),
    enabled: Boolean(session.data?.store_id) && isQueryReady(query),
  });
  if (session.isLoading) return <LoadingBoard />;
  if (session.isError) return <ErrorBoard message={(session.error as Error).message} />;
  if (!isQueryReady(query)) return <CustomRangePrompt title="Inventory" />;
  if (request.isLoading) return <LoadingBoard />;
  if (request.isError) return <ErrorBoard message={(request.error as Error).message} />;
  const data = request.data;
  if (!data || data.inventory.tracked_variants === 0) {
    return (
      <div className="grid gap-4">
        <h1 className="text-xl font-semibold">Inventory</h1>
        <DateRangeBar />
        <EmptyBoard title="No inventory snapshots" body="Run a sync so available and on-hand quantities can be projected." />
      </div>
    );
  }
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Inventory</h1>
      <DateRangeBar />
      <Card>
        <CardHeader>
          <CardTitle>Coverage</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm">
          <p>{data.inventory.in_stock_variants} in stock · {data.inventory.out_of_stock_variants} out of stock</p>
          <p className="text-[hsl(var(--muted-foreground))]">
            Utilization {data.inventory.utilization_pct ?? "—"}% of on-hand units
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Selling variants</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {data.products.length === 0 ? (
            <p className="text-sm text-[hsl(var(--muted-foreground))]">No product sales to pair with inventory.</p>
          ) : (
            <table className="w-full min-w-[28rem] text-left text-sm">
              <caption className="sr-only">Product availability for the current range</caption>
              <thead className="text-xs text-[hsl(var(--muted-foreground))]">
                <tr>
                  <th className="pb-2 font-medium">Product</th>
                  <th className="pb-2 font-medium">Units sold</th>
                  <th className="pb-2 font-medium">Available</th>
                  <th className="pb-2 font-medium">Revenue</th>
                </tr>
              </thead>
              <tbody>
                {data.products.map((row) => (
                  <tr key={row.product_gid} className="border-t">
                    <td className="py-2">{row.title}</td>
                    <td className="tabular-nums">{row.units_sold}</td>
                    <td className="tabular-nums">{row.available ?? "—"}</td>
                    <td className="tabular-nums">{formatMoney(row.revenue, data.store.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function CustomersView() {
  const query = useAnalyticsQuery();
  const session = useSessionStore();
  const request = useQuery({
    queryKey: ["analytics-customers", session.data?.store_id, query],
    queryFn: () => fetchCustomers(query),
    enabled: Boolean(session.data?.store_id) && isQueryReady(query),
  });
  if (session.isLoading) return <LoadingBoard />;
  if (session.isError) return <ErrorBoard message={(session.error as Error).message} />;
  if (!isQueryReady(query)) return <CustomRangePrompt title="Customers" />;
  if (request.isLoading) return <LoadingBoard />;
  if (request.isError) return <ErrorBoard message={(request.error as Error).message} />;
  const data = request.data;
  if (!data || data.kpis.customers === 0) {
    return (
      <div className="grid gap-4">
        <h1 className="text-xl font-semibold">Customers</h1>
        <DateRangeBar />
        <EmptyBoard title="No ordering customers" body="Customer emails are never shown on this screen." />
      </div>
    );
  }
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Customers</h1>
      <DateRangeBar />
      <Card>
        <CardContent className="grid gap-2 pt-4 text-sm">
          <p>Ordering customers {data.kpis.customers}</p>
          <p>New {data.kpis.new_customers} · Returning {data.kpis.returning_customers}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Customer trend</CardTitle>
        </CardHeader>
        <CardContent>
          <TrendChart
            label="Ordering customers by day"
            dataKey="customers"
            empty={data.trend.length === 0}
            data={data.trend}
          />
        </CardContent>
      </Card>
    </div>
  );
}

export function InsightsView() {
  const query = useAnalyticsQuery();
  const session = useSessionStore();
  const request = useQuery({
    queryKey: ["analytics-overview", session.data?.store_id, query],
    queryFn: () => fetchOverview(query),
    enabled: Boolean(session.data?.store_id) && isQueryReady(query),
  });
  if (session.isLoading) return <LoadingBoard />;
  if (session.isError) return <ErrorBoard message={(session.error as Error).message} />;
  if (!isQueryReady(query)) return <CustomRangePrompt title="Insights" />;
  if (request.isLoading) return <LoadingBoard />;
  if (request.isError) return <ErrorBoard message={(request.error as Error).message} />;
  const rows = request.data?.opportunities ?? [];
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Insights</h1>
      <DateRangeBar />
      {rows.length === 0 ? (
        <EmptyBoard title="No opportunities" body="Deterministic rules found nothing to surface for this range." />
      ) : (
        rows.map((row) => (
          <Card key={row.key}>
            <CardHeader>
              <CardTitle>{row.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-[hsl(var(--muted-foreground))]">{row.explanation}</CardContent>
          </Card>
        ))
      )}
    </div>
  );
}

export function ActionsPlaceholder() {
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Actions</h1>
      <EmptyBoard
        title="Approval-gated actions are not in Phase 4"
        body="This page is navigation only. Shopify mutations stay out of this release."
      />
    </div>
  );
}

export function SettingsView() {
  const session = useSessionStore();
  const request = useQuery({
    queryKey: ["settings", session.data?.store_id],
    queryFn: () =>
      fetchJson<{ shop_domain: string; installed: boolean; scopes: string[] }>("/api/v1/settings"),
    enabled: Boolean(session.data?.store_id),
  });
  if (session.isLoading || request.isLoading) return <LoadingBoard />;
  if (session.isError) return <ErrorBoard message={(session.error as Error).message} />;
  if (request.isError) return <ErrorBoard message={(request.error as Error).message} />;
  const data = request.data;
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Settings</h1>
      <Card>
        <CardContent className="grid gap-2 pt-4 text-sm">
          <p>Connection: Shopify</p>
          <p>Shop: {data?.shop_domain}</p>
          <p>Installed: {data?.installed ? "yes" : "no"}</p>
          <p>Scopes: {data?.scopes.join(", ")}</p>
        </CardContent>
      </Card>
    </div>
  );
}

