export type DatePreset =
  | "today"
  | "yesterday"
  | "last_7"
  | "last_30"
  | "last_90"
  | "this_month"
  | "previous_month"
  | "custom";

export type CompareMode = "previous_period" | "previous_month";

export type AnalyticsQuery = {
  preset: DatePreset;
  compare: CompareMode;
  from?: string;
  to?: string;
};

export type OverviewResponse = {
  request_id: string;
  store: {
    store_id: string;
    shop_domain: string;
    timezone: string;
    currency: string;
    installed: boolean;
    sync_status: string;
  };
  range: {
    current: { start_local: string; end_local_exclusive: string; timezone: string };
    previous: { start_local: string; end_local_exclusive: string };
    compare: CompareMode;
  };
  kpis: {
    revenue: string;
    orders: number;
    aov: string | null;
    customers: number;
    new_customers: number;
    returning_customers: number;
    cancelled_orders: number;
    growth_pct: {
      revenue: string | null;
      orders: string | null;
      customers: string | null;
      aov: string | null;
    };
    previous: { revenue: string; orders: number; aov: string | null; customers: number };
  };
  trends: {
    revenue: { date: string; revenue: string; orders: number }[];
    customers: { date: string; customers: number }[];
  };
  products: {
    product_gid: string;
    title: string;
    status: string;
    units_sold: number;
    revenue: string;
    available: number | null;
  }[];
  inventory: {
    tracked_variants: number;
    in_stock_variants: number;
    out_of_stock_variants: number;
    available_units: number;
    on_hand_units: number;
    utilization_pct: string | null;
  };
  health: {
    score: number | null;
    status: string;
    summary: string;
    label: string;
    components: {
      key: string;
      label: string;
      weight: string;
      score: number;
      explanation: string;
    }[];
  };
  opportunities: {
    key: string;
    title: string;
    explanation: string;
    metric: string;
    severity: string;
    detected_at: string;
    evidence: { metric: string; value: string }[];
  }[];
};

export type SessionContext = {
  store_id: string;
  shop_domain: string;
  installed?: boolean;
};

export function fetchSession(): Promise<SessionContext> {
  return fetchJson("/api/v1/me");
}

export type ProductsResponse = {
  total: number;
  limit: number;
  offset: number;
  items: OverviewResponse["products"];
};

export function isQueryReady(query: AnalyticsQuery): boolean {
  return query.preset !== "custom" || Boolean(query.from && query.to);
}

export function analyticsSearch(query: AnalyticsQuery): string {
  const params = new URLSearchParams({ preset: query.preset, compare: query.compare });
  if (query.preset === "custom" && query.from && query.to) {
    params.set("from", query.from);
    params.set("to", query.to);
  }
  return params.toString();
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: "include" });
  if (response.status === 401) {
    throw new Error("Sign in by installing MerchantOS on your Shopify store.");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? "We could not load this view. Try again.");
  }
  return (await response.json()) as T;
}

export function isAuthError(error: unknown): boolean {
  return error instanceof Error && error.message.includes("installing MerchantOS");
}

export function fetchOverview(query: AnalyticsQuery): Promise<OverviewResponse> {
  return fetchJson(`/api/v1/analytics/overview?${analyticsSearch(query)}`);
}

export function fetchCustomers(query: AnalyticsQuery): Promise<
  Pick<OverviewResponse, "store" | "range" | "kpis"> & {
    trend: OverviewResponse["trends"]["customers"];
  }
> {
  return fetchJson(`/api/v1/analytics/customers?${analyticsSearch(query)}`);
}

export function fetchProducts(
  query: AnalyticsQuery,
  page: { limit: number; offset: number; sort: string },
): Promise<ProductsResponse> {
  const params = new URLSearchParams(analyticsSearch(query));
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  params.set("sort", page.sort);
  return fetchJson(`/api/v1/analytics/products?${params.toString()}`);
}

export function formatMoney(value: string | null, currency = "USD"): string {
  if (value == null) return "—";
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
}

export function formatPct(value: string | null): string {
  if (value == null) return "—";
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  const sign = amount > 0 ? "+" : "";
  return `${sign}${amount.toFixed(1)}%`;
}
