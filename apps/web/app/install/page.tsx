"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { isValidShopDomain, normalizeShopDomain } from "@/lib/shop-domain";

function InstallForm() {
  const params = useSearchParams();
  const installed = params.get("installed") === "1";
  const failed = params.get("installed") === "0";
  const [shop, setShop] = useState(params.get("shop") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const valid = isValidShopDomain(shop);

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6 py-16">
      <p className="text-xs font-medium uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
        MerchantOS
      </p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Connect your Shopify store</h1>
      <p className="mt-4 text-[hsl(var(--muted-foreground))]">
        Install MerchantOS with official Shopify sign-in. Your store password and access token
        never appear on this page.
      </p>
      {installed ? (
        <p
          role="status"
          className="mt-6 rounded-lg border border-emerald-600/30 bg-emerald-50 p-4 text-emerald-950 dark:bg-emerald-950/30 dark:text-emerald-100"
        >
          Store connected. You can open Overview and import store data.
        </p>
      ) : null}
      {failed ? (
        <p
          role="alert"
          className="mt-6 rounded-lg border border-[hsl(var(--danger))]/40 p-4 text-[hsl(var(--danger))]"
        >
          We could not finish install. {params.get("reason") ?? "Use a valid your-store.myshopify.com domain and try again."}
        </p>
      ) : null}
      <Card className="mt-8">
        <CardContent className="grid gap-4 pt-6">
          <form
            className="grid gap-3"
            action="/api/v1/auth/shopify/install"
            method="get"
            onSubmit={(event) => {
              const next = normalizeShopDomain(shop);
              if (!isValidShopDomain(next)) {
                event.preventDefault();
                setError("Enter a store as your-store.myshopify.com.");
                return;
              }
              setError(null);
              setPending(true);
            }}
          >
            <label className="grid gap-2 text-sm" htmlFor="shop">
              <span className="font-medium">Store domain</span>
              <input
                id="shop"
                name="shop"
                value={shop}
                onChange={(event) => {
                  setShop(event.target.value);
                  setError(null);
                }}
                placeholder="your-store.myshopify.com"
                autoComplete="off"
                spellCheck={false}
                required
                aria-invalid={Boolean(error) || (shop.length > 0 && !valid)}
                aria-describedby="shop-help"
                className="h-11 w-full rounded-md border bg-[hsl(var(--background))] px-3"
              />
            </label>
            <p id="shop-help" className="text-xs text-[hsl(var(--muted-foreground))]">
              Use the myshopify.com domain, not a custom website URL.
            </p>
            {error ? (
              <p role="alert" className="text-sm text-[hsl(var(--danger))]">
                {error}
              </p>
            ) : null}
            <Button type="submit" className="h-11" disabled={pending}>
              {pending ? "Redirecting to Shopify…" : "Install MerchantOS"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

export default function InstallPage() {
  return (
    <Suspense fallback={<main className="mx-auto max-w-xl px-6 py-16">Loading install…</main>}>
      <InstallForm />
    </Suspense>
  );
}
