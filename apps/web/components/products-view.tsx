"use client";

import { useQuery } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { DateRangeBar } from "@/components/date-range-bar";
import { EmptyBoard, ErrorBoard, LoadingBoard } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type AnalyticsQuery,
  type CompareMode,
  type DatePreset,
  fetchProducts,
  formatMoney,
  isQueryReady,
} from "@/lib/analytics";
import { useSessionStore } from "@/lib/use-session-store";

type Row = {
  product_gid: string;
  title: string;
  status: string;
  units_sold: number;
  revenue: string;
  available: number | null;
};

export function ProductsView() {
  const params = useSearchParams();
  const query: AnalyticsQuery = {
    preset: (params.get("preset") as DatePreset) || "last_30",
    compare: (params.get("compare") as CompareMode) || "previous_period",
    from: params.get("from") ?? undefined,
    to: params.get("to") ?? undefined,
  };
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState("revenue");
  const limit = 25;
  const session = useSessionStore();
  const request = useQuery({
    queryKey: ["analytics-products", session.data?.store_id, query, offset, sort],
    queryFn: () => fetchProducts(query, { limit, offset, sort }),
    enabled: Boolean(session.data?.store_id) && isQueryReady(query),
  });
  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      { accessorKey: "title", header: "Product" },
      { accessorKey: "status", header: "Status" },
      { accessorKey: "units_sold", header: "Units" },
      {
        accessorKey: "revenue",
        header: "Revenue",
        cell: ({ getValue }) => formatMoney(String(getValue())),
      },
      {
        accessorKey: "available",
        header: "Available",
        cell: ({ getValue }) => (getValue() == null ? "—" : String(getValue())),
      },
    ],
    [],
  );
  const table = useReactTable({
    data: request.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  if (session.isLoading) return <LoadingBoard />;
  if (session.isError) return <ErrorBoard message={(session.error as Error).message} />;
  if (!isQueryReady(query)) {
    return (
      <div className="grid gap-4">
        <h1 className="text-xl font-semibold">Products</h1>
        <DateRangeBar />
        <EmptyBoard title="Choose a custom range" body="Pick a start and end date. Both days are inclusive." />
      </div>
    );
  }
  if (request.isLoading) return <LoadingBoard />;
  if (request.isError) return <ErrorBoard message={(request.error as Error).message} />;
  const data = request.data;
  if (!data || data.items.length === 0) {
    return (
      <div className="grid gap-4">
        <h1 className="text-xl font-semibold">Products</h1>
        <DateRangeBar />
        <EmptyBoard title="No products" body="Sync the catalog or wait for the first projection." />
      </div>
    );
  }
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Products</h1>
      <DateRangeBar />
      <div className="flex flex-wrap gap-2">
        {(["revenue", "units", "title", "available"] as const).map((key) => (
          <Button key={key} size="sm" variant={sort === key ? "default" : "outline"} onClick={() => setSort(key)}>
            Sort: {key}
          </Button>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>
            {data.total} products · showing {data.offset + 1}–{Math.min(data.offset + data.limit, data.total)}
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="text-xs text-[hsl(var(--muted-foreground))]">
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => (
                    <th key={header.id} className="pb-2 font-medium">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-t">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="py-2">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4 flex gap-2">
            <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={offset + limit >= data.total}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
