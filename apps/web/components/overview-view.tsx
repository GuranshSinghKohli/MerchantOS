"use client";

import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import { useSearchParams } from "next/navigation";
import { DateRangeBar } from "@/components/date-range-bar";
import { ConnectStoreBoard, EmptyStoreBoard } from "@/components/empty-store";
import { EmptyBoard, ErrorBoard, LoadingBoard } from "@/components/states";
import { TrendChart } from "@/components/trend-chart";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type AnalyticsQuery,
  type CompareMode,
  type DatePreset,
  fetchOverview,
  formatMoney,
  formatPct,
  isAuthError,
  isQueryReady,
} from "@/lib/analytics";
import { neverSynced, syncStatusLabel } from "@/lib/labels";
import { useSessionStore } from "@/lib/use-session-store";

function queryFromParams(params: URLSearchParams): AnalyticsQuery {
  return {
    preset: (params.get("preset") as DatePreset) || "last_30",
    compare: (params.get("compare") as CompareMode) || "previous_period",
    from: params.get("from") ?? undefined,
    to: params.get("to") ?? undefined,
  };
}

function Kpi({
  label,
  value,
  delta,
}: {
  label: string;
  value: string;
  delta: string | null;
}) {
  const tone =
    delta == null ? "text-[hsl(var(--muted-foreground))]" : Number(delta) < 0 ? "text-[hsl(var(--danger))]" : "text-[hsl(var(--accent))]";
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-[hsl(var(--muted-foreground))]">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
        <p className={`mt-1 text-xs tabular-nums ${tone}`}>
          {formatPct(delta)} vs comparison
        </p>
      </CardContent>
    </Card>
  );
}

export function OverviewView() {
  const params = useSearchParams();
  const query = queryFromParams(params);
  const reduced = useReducedMotion();
  const session = useSessionStore();
  const request = useQuery({
    queryKey: ["analytics-overview", session.data?.store_id, query],
    queryFn: () => fetchOverview(query),
    enabled: Boolean(session.data?.store_id) && isQueryReady(query),
  });

  if (session.isLoading) return <LoadingBoard />;
  if (session.isError) {
    if (isAuthError(session.error)) return <ConnectStoreBoard />;
    return <ErrorBoard message={(session.error as Error).message} />;
  }
  if (!isQueryReady(query)) {
    return (
      <div className="grid gap-4">
        <DateRangeBar />
        <EmptyBoard title="Choose a custom range" body="Pick a start and end date. Both days are inclusive." />
      </div>
    );
  }
  if (request.isLoading) return <LoadingBoard />;
  if (request.isError) return <ErrorBoard message={(request.error as Error).message} />;
  const data = request.data;
  if (!data) return <LoadingBoard />;
  if (neverSynced(data.store.sync_status)) {
    return (
      <div className="grid gap-4">
        <StoreHeader data={data} />
        <EmptyStoreBoard shopDomain={data.store.shop_domain} syncStatus={data.store.sync_status} />
      </div>
    );
  }
  if (data.kpis.orders === 0) {
    return (
      <div className="grid gap-4">
        <StoreHeader data={data} />
        <DateRangeBar />
        <EmptyBoard
          title="No orders in this date range"
          body="MerchantOS is connected. There are no included paid orders in the selected dates. Widen the range, or import store data again from Settings."
        />
      </div>
    );
  }

  return (
    <motion.div
      className="grid gap-6"
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <StoreHeader data={data} />
      <DateRangeBar />
      <section aria-label="Key metrics" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Revenue" value={formatMoney(data.kpis.revenue, data.store.currency)} delta={data.kpis.growth_pct.revenue} />
        <Kpi label="Orders" value={String(data.kpis.orders)} delta={data.kpis.growth_pct.orders} />
        <Kpi
          label="AOV"
          value={formatMoney(data.kpis.aov, data.store.currency)}
          delta={data.kpis.growth_pct.aov}
        />
        <Kpi label="Customers" value={String(data.kpis.customers)} delta={data.kpis.growth_pct.customers} />
      </section>
      <section className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Revenue trend</CardTitle>
          </CardHeader>
          <CardContent>
            <TrendChart
              label="Revenue by day"
              dataKey="revenue"
              empty={data.trends.revenue.length === 0}
              data={data.trends.revenue.map((row) => ({ date: row.date, revenue: Number(row.revenue) }))}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Orders trend</CardTitle>
          </CardHeader>
          <CardContent>
            <TrendChart
              label="Orders by day"
              dataKey="orders"
              empty={data.trends.revenue.length === 0}
              data={data.trends.revenue.map((row) => ({ date: row.date, orders: row.orders }))}
            />
          </CardContent>
        </Card>
      </section>
      <section className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top products</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            {data.products.length === 0 ? (
              <p className="text-sm text-[hsl(var(--muted-foreground))]">No product sales in this range.</p>
            ) : (
              <table className="w-full min-w-[28rem] text-left text-sm">
                <caption className="sr-only">Top products by revenue</caption>
                <thead className="text-xs text-[hsl(var(--muted-foreground))]">
                  <tr>
                    <th className="pb-2 font-medium">Product</th>
                    <th className="pb-2 font-medium">Units</th>
                    <th className="pb-2 font-medium">Revenue</th>
                    <th className="pb-2 font-medium">Available</th>
                  </tr>
                </thead>
                <tbody>
                  {data.products.map((row) => (
                    <tr key={row.product_gid} className="border-t">
                      <td className="py-2">{row.title}</td>
                      <td className="tabular-nums">{row.units_sold}</td>
                      <td className="tabular-nums">{formatMoney(row.revenue, data.store.currency)}</td>
                      <td className="tabular-nums">{row.available ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Inventory health</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            <p>{data.inventory.in_stock_variants} of {data.inventory.tracked_variants} tracked variants in stock</p>
            <p className="text-[hsl(var(--muted-foreground))]">
              Utilization {data.inventory.utilization_pct ?? "—"}% · available {data.inventory.available_units} / on hand {data.inventory.on_hand_units}
            </p>
          </CardContent>
        </Card>
      </section>
      <section className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Customers</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            <p>New {data.kpis.new_customers} · Returning {data.kpis.returning_customers}</p>
            <TrendChart
              label="Ordering customers by day"
              dataKey="customers"
              empty={data.trends.customers.length === 0}
              data={data.trends.customers}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{data.health.label}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <p className="text-3xl font-semibold tabular-nums">{data.health.score ?? "—"}</p>
            <p className="text-[hsl(var(--muted-foreground))]">{data.health.summary}</p>
            <ul className="grid gap-2">
              {data.health.components.map((row) => (
                <li key={row.key}>
                  <span className="font-medium">{row.label}</span>
                  <span className="text-[hsl(var(--muted-foreground))]"> · {row.score} · {row.explanation}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>
      <section>
        <Card>
          <CardHeader>
            <CardTitle>Opportunities</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            {data.opportunities.length === 0 ? (
              <p className="text-sm text-[hsl(var(--muted-foreground))]">No rule-based opportunities for this range.</p>
            ) : (
              data.opportunities.map((row) => (
                <article key={row.key} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-medium">{row.title}</h3>
                    <Badge>{row.severity}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-[hsl(var(--muted-foreground))]">{row.explanation}</p>
                  <p className="mt-2 text-xs text-[hsl(var(--muted-foreground))]">
                    {row.metric} · {row.detected_at} · {row.evidence.map((item) => `${item.metric}=${item.value}`).join(" · ")}
                  </p>
                </article>
              ))
            )}
          </CardContent>
        </Card>
      </section>
    </motion.div>
  );
}

function StoreHeader({ data }: { data: Awaited<ReturnType<typeof fetchOverview>> }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{data.store.shop_domain}</h1>
        <p className="text-sm text-[hsl(var(--muted-foreground))]">
          {data.range.current.start_local} → {data.range.current.end_local_exclusive} · {data.store.timezone}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Badge>{data.store.installed ? "Connected" : "Disconnected"}</Badge>
        <Badge>{syncStatusLabel(data.store.sync_status)}</Badge>
      </div>
    </div>
  );
}
