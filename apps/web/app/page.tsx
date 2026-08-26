import { fetchHealth } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let health: { status: string; version: string } | null = null;
  let error: string | null = null;
  try {
    health = await fetchHealth();
  } catch (cause) {
    error = cause instanceof Error ? cause.message : "API unreachable";
  }

  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <p className="text-sm uppercase tracking-wide text-zinc-500">MerchantOS</p>
      <h1 className="mt-2 text-3xl font-semibold">Phase 1 foundation</h1>
      <p className="mt-4 text-zinc-600">
        This page reports the live API health probe. It is not a store dashboard
        and does not use mock commerce data.
      </p>
      <section className="mt-8 rounded-lg border border-zinc-200 bg-white p-4">
        <h2 className="text-sm font-medium text-zinc-500">GET /health</h2>
        {health ? (
          <p className="mt-2 text-zinc-900">
            {health.status} · version {health.version}
          </p>
        ) : (
          <p className="mt-2 text-red-700">{error}</p>
        )}
      </section>
    </main>
  );
}
