"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function TrendChart({
  data,
  dataKey,
  label,
  empty,
}: {
  data: Record<string, string | number>[];
  dataKey: string;
  label: string;
  empty: boolean;
}) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);
  if (empty) {
    return (
      <p className="py-10 text-center text-sm text-[hsl(var(--muted-foreground))]">
        {label}: no points in range.
      </p>
    );
  }
  if (!ready) {
    return <div className="h-64 w-full" aria-busy="true" aria-label={`Loading ${label}`} />;
  }
  return (
    <div className="h-64 w-full min-w-0" role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height={256} minWidth={1}>
        <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} width={48} />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          <Line type="monotone" dataKey={dataKey} stroke="hsl(var(--accent))" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
