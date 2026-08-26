type Search = { shop?: string; installed?: string; reason?: string };

export const dynamic = "force-dynamic";

export default async function InstallPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const params = await searchParams;
  const installed = params.installed === "1";
  const failed = params.installed === "0";

  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <p className="text-sm uppercase tracking-wide text-zinc-500">MerchantOS</p>
      <h1 className="mt-2 text-3xl font-semibold">Install on Shopify</h1>
      <p className="mt-4 text-zinc-600">
        This starts the official Shopify authorization code grant. Access tokens
        never reach this page.
      </p>
      {installed ? (
        <p className="mt-6 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">
          Installation succeeded. Your store is linked.
        </p>
      ) : null}
      {failed ? (
        <p className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
          Installation failed. {params.reason ?? "Try again from a valid shop domain."}
        </p>
      ) : null}
      <form className="mt-8 space-y-3" action="/api/v1/auth/shopify/install" method="get">
        <label className="block text-sm font-medium text-zinc-700" htmlFor="shop">
          Shop domain
        </label>
        <input
          id="shop"
          name="shop"
          defaultValue={params.shop ?? ""}
          placeholder="your-store.myshopify.com"
          className="w-full rounded-md border border-zinc-300 px-3 py-2"
          required
        />
        <button
          type="submit"
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm text-white"
        >
          Install MerchantOS
        </button>
      </form>
    </main>
  );
}
