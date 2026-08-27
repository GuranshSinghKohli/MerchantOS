"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { EmptyBoard, ErrorBoard, LoadingBoard } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type ActionRecord,
  approveAction,
  changedFields,
  displayValue,
  fetchActions,
  fetchPendingApprovals,
  fieldLabel,
  rejectAction,
} from "@/lib/actions";
import { useSessionStore } from "@/lib/use-session-store";

const IN_FLIGHT = new Set(["QUEUED", "EXECUTING"]);
const STEPS = ["PROPOSED", "QUEUED", "EXECUTING", "COMPLETED"] as const;

function statusTone(status: string): string {
  if (status === "COMPLETED") return "border-emerald-600/40 text-emerald-700 dark:text-emerald-300";
  if (status === "FAILED" || status === "CONFLICT" || status === "EXPIRED") {
    return "border-[hsl(var(--danger))]/40 text-[hsl(var(--danger))]";
  }
  if (status === "REJECTED" || status === "BLOCKED") {
    return "text-[hsl(var(--muted-foreground))]";
  }
  return "border-[hsl(var(--accent))]/40 text-[hsl(var(--accent))]";
}

function ActionCard({
  action,
  onApprove,
  onReject,
  busy,
}: {
  action: ActionRecord;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  busy: boolean;
}) {
  const [ackHigh, setAckHigh] = useState(false);
  const fields = changedFields(action.before_state, action.after_state);
  const pending = action.status === "PROPOSED";
  const highRisk = action.risk_level === "HIGH" || action.risk_level === "CRITICAL";
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <CardTitle>{action.title}</CardTitle>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            {fieldLabel(fields[0] ?? "title")} on {action.resource.gid}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge className={statusTone(action.status)}>{action.status}</Badge>
          <Badge>{action.risk_level} risk</Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        <section className="grid gap-2">
          <h2 className="font-medium">What will change?</h2>
          {fields.length === 0 ? (
            <p className="text-[hsl(var(--muted-foreground))]">No field difference is recorded.</p>
          ) : (
            fields.map((field) => (
              <div key={field} className="grid gap-1 rounded-md border p-3">
                <p className="text-xs uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
                  {fieldLabel(field)}
                </p>
                <p>
                  <span className="text-[hsl(var(--muted-foreground))]">Current: </span>
                  {displayValue(action.before_state[field])}
                </p>
                <p>
                  <span className="text-[hsl(var(--muted-foreground))]">Proposed: </span>
                  {displayValue(action.after_state[field])}
                </p>
              </div>
            ))
          )}
        </section>
        <section className="grid gap-1">
          <h2 className="font-medium">Where will it change?</h2>
          <p>Shopify product {action.resource.gid}</p>
        </section>
        <section className="grid gap-1">
          <h2 className="font-medium">Why is MerchantOS recommending this?</h2>
          <p>{action.rationale}</p>
          {action.source_recommendation_id ? (
            <p className="text-[hsl(var(--muted-foreground))]">
              Source recommendation {action.source_recommendation_id}
            </p>
          ) : null}
          {action.evidence.length > 0 ? (
            <ul className="list-disc pl-5 text-[hsl(var(--muted-foreground))]">
              {action.evidence.map((item, index) => (
                <li key={`${item.fact_id ?? "e"}-${index}`}>
                  {item.source_tool ?? "evidence"} {item.fact_id ?? ""}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          Created {action.created_at ?? "—"}
          {action.expires_at ? ` · Expires ${action.expires_at}` : ""}
        </p>
        {IN_FLIGHT.has(action.status) || action.status === "COMPLETED" || action.status === "FAILED" ? (
          <ol className="flex flex-wrap gap-2 text-xs" aria-label="Execution status">
            {STEPS.map((step) => (
              <li
                key={step}
                className={
                  action.status === step || (step === "COMPLETED" && action.status === "FAILED")
                    ? "font-medium"
                    : "text-[hsl(var(--muted-foreground))]"
                }
              >
                {step === "PROPOSED" ? "Pending" : step.charAt(0) + step.slice(1).toLowerCase()}
              </li>
            ))}
          </ol>
        ) : null}
        {action.error_message ? (
          <p className="text-[hsl(var(--danger))]">{action.error_message}</p>
        ) : null}
        {pending ? (
          <div className="grid gap-3 border-t pt-3">
            {highRisk ? (
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={ackHigh}
                  onChange={(event) => setAckHigh(event.target.checked)}
                />
                I understand this is a high-risk change to a live Shopify product.
              </label>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" disabled={busy} onClick={() => onReject(action.action_id)}>
                Reject
              </Button>
              <Button
                disabled={busy || (highRisk && !ackHigh)}
                onClick={() => onApprove(action.action_id)}
              >
                Approve Change
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function ActionsView({ pendingOnly = false }: { pendingOnly?: boolean }) {
  const session = useSessionStore();
  const client = useQueryClient();
  const request = useQuery({
    queryKey: [pendingOnly ? "approvals" : "actions", session.data?.store_id],
    queryFn: pendingOnly ? fetchPendingApprovals : fetchActions,
    enabled: Boolean(session.data?.store_id),
    refetchInterval: (query) => {
      const rows = query.state.data?.actions ?? [];
      return rows.some((row) => IN_FLIGHT.has(row.status)) ? 2000 : false;
    },
  });
  const decide = useMutation({
    mutationFn: async ({ id, decision }: { id: string; decision: "approve" | "reject" }) => {
      return decision === "approve" ? approveAction(id) : rejectAction(id);
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["actions"] });
      void client.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
  if (session.isLoading || request.isLoading) return <LoadingBoard />;
  if (session.isError) return <ErrorBoard message={(session.error as Error).message} />;
  if (request.isError) return <ErrorBoard message={(request.error as Error).message} />;
  const rows = request.data?.actions ?? [];
  const title = pendingOnly ? "Approvals" : "Actions";
  return (
    <div className="grid gap-4">
      <div className="grid gap-1">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-[hsl(var(--muted-foreground))]">
          MerchantOS can propose a Shopify product change. Only you can approve it. The model
          cannot execute the mutation.
        </p>
      </div>
      {decide.isError ? <ErrorBoard message={(decide.error as Error).message} /> : null}
      {rows.length === 0 ? (
        <EmptyBoard
          title={pendingOnly ? "No actions waiting for review" : "No actions yet"}
          body="Proposed product changes appear here with the current value, the proposed value, and an explicit Approve Change control."
        />
      ) : (
        rows.map((action) => (
          <ActionCard
            key={action.action_id}
            action={action}
            busy={decide.isPending}
            onApprove={(id) => decide.mutate({ id, decision: "approve" })}
            onReject={(id) => decide.mutate({ id, decision: "reject" })}
          />
        ))
      )}
    </div>
  );
}
