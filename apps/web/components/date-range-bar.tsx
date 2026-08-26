"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { CompareMode, DatePreset } from "@/lib/analytics";

const PRESETS: { value: DatePreset; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "last_7", label: "Last 7 days" },
  { value: "last_30", label: "Last 30 days" },
  { value: "last_90", label: "Last 90 days" },
  { value: "this_month", label: "This month" },
  { value: "previous_month", label: "Previous month" },
  { value: "custom", label: "Custom" },
];

export function DateRangeBar() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const preset = (params.get("preset") as DatePreset) || "last_30";
  const compare = (params.get("compare") as CompareMode) || "previous_period";

  function update(next: Record<string, string>) {
    const merged = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value);
      else merged.delete(key);
    }
    router.replace(`${pathname}?${merged.toString()}`);
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
      <label className="grid gap-1 text-xs text-[hsl(var(--muted-foreground))]">
        Date range
        <select
          className="h-9 rounded-md border bg-[hsl(var(--card))] px-2 text-sm text-[hsl(var(--foreground))]"
          value={preset}
          onChange={(event) => update({ preset: event.target.value })}
        >
          {PRESETS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-xs text-[hsl(var(--muted-foreground))]">
        Compare
        <select
          className="h-9 rounded-md border bg-[hsl(var(--card))] px-2 text-sm text-[hsl(var(--foreground))]"
          value={compare}
          onChange={(event) => update({ compare: event.target.value })}
        >
          <option value="previous_period">Previous period</option>
          <option value="previous_month">Previous month</option>
        </select>
      </label>
      {preset === "custom" ? (
        <>
          <label className="grid gap-1 text-xs text-[hsl(var(--muted-foreground))]">
            From
            <input
              type="date"
              className="h-9 rounded-md border bg-[hsl(var(--card))] px-2 text-sm"
              value={params.get("from") ?? ""}
              onChange={(event) => update({ from: event.target.value, preset: "custom" })}
            />
          </label>
          <label className="grid gap-1 text-xs text-[hsl(var(--muted-foreground))]">
            To
            <input
              type="date"
              className="h-9 rounded-md border bg-[hsl(var(--card))] px-2 text-sm"
              value={params.get("to") ?? ""}
              onChange={(event) => update({ to: event.target.value, preset: "custom" })}
            />
          </label>
        </>
      ) : null}
    </div>
  );
}
