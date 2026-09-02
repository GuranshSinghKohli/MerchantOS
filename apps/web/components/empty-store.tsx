"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { syncInFlight, syncStatusLabel } from "@/lib/labels";
import { startStoreImport } from "@/lib/sync";

export function EmptyStoreBoard({
  shopDomain,
  syncStatus,
}: {
  shopDomain: string;
  syncStatus: string;
}) {
  const client = useQueryClient();
  const importStore = useMutation({
    mutationFn: startStoreImport,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["analytics-overview"] });
      void client.invalidateQueries({ queryKey: ["sync-status"] });
    },
  });
  const inFlight = syncInFlight(syncStatus);
  const importing = importStore.isPending;
  return (
    <Card>
      <CardContent className="grid gap-4 py-10 text-center">
        <div className="grid gap-2">
          <p className="text-sm font-medium">Import your Shopify store to see insights</p>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            {syncStatus === "failed"
              ? `${shopDomain} is connected, but the last import did not finish. Try Import again.`
              : `${shopDomain} is connected, but MerchantOS has not imported catalog and order data yet. Numbers stay hidden until that import finishes so empty zeros are not mistaken for real activity.`}
          </p>
          <p className="text-xs text-[hsl(var(--muted-foreground))]">
            Import status: {syncStatusLabel(syncStatus)}
          </p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          <Button
            disabled={importing}
            onClick={() => importStore.mutate()}
            aria-busy={importing}
          >
            {importing
              ? "Importing store data…"
              : inFlight
                ? "Retry import"
                : "Import store data"}
          </Button>
          {syncStatus === "failed" ? (
            <Button variant="outline" asChild>
              <Link href="/install">Install again</Link>
            </Button>
          ) : (
            <Button variant="outline" asChild>
              <Link href="/ask">Ask a question anyway</Link>
            </Button>
          )}
        </div>
        {importStore.isError ? (
          <p className="text-sm text-[hsl(var(--danger))]">
            {(importStore.error as Error).message}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function ConnectStoreBoard() {
  return (
    <Card>
      <CardContent className="grid gap-4 py-10 text-center">
        <p className="text-sm font-medium">Connect your Shopify store</p>
        <p className="text-sm text-[hsl(var(--muted-foreground))]">
          MerchantOS reads your store through official Shopify OAuth. Sign in by installing the
          app. Access tokens never appear in this browser.
        </p>
        <div>
          <Button asChild>
            <Link href="/install">Install MerchantOS</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
