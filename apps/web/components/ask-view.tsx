"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ConnectStoreBoard } from "@/components/empty-store";
import { EmptyBoard, ErrorBoard, LoadingBoard } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type IntelligenceResult,
  type IntelligenceRun,
  evidenceFor,
  fetchIntelligence,
  listIntelligence,
  startIntelligence,
} from "@/lib/intelligence";
import { isAuthError } from "@/lib/analytics";
import { agentLabel, confidenceLabel } from "@/lib/labels";
import { useSessionStore } from "@/lib/use-session-store";

const SUGGESTIONS = [
  "How is my store doing?",
  "Why is my revenue down?",
  "Are inventory issues affecting performance?",
];

function RunStatus({ status }: { status: string }) {
  if (status === "COMPLETED") return <Badge>Ready</Badge>;
  if (status === "FAILED" || status === "CANCELLED") {
    return <Badge className="border-[hsl(var(--danger))]/40 text-[hsl(var(--danger))]">{status === "FAILED" ? "Could not finish" : "Cancelled"}</Badge>;
  }
  return <Badge>Working…</Badge>;
}

function EvidenceList({
  ids,
  evidence,
}: {
  ids: string[];
  evidence: IntelligenceResult["evidence"];
}) {
  const rows = evidenceFor(ids, evidence);
  if (rows.length === 0) return null;
  return (
    <details className="rounded-md border p-3">
      <summary className="cursor-pointer text-sm font-medium">Supporting evidence</summary>
      <ul className="mt-2 grid gap-2 text-sm text-[hsl(var(--muted-foreground))]">
        {rows.map((item) => (
          <li key={item.id}>{item.fact}</li>
        ))}
      </ul>
    </details>
  );
}

function Report({ result }: { result: IntelligenceResult }) {
  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
          <CardTitle>Answer</CardTitle>
          <Badge>{confidenceLabel(result.confidence)}</Badge>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm">
          <p>{result.executive_summary}</p>
          {result.selected_agents.length > 0 ? (
            <p className="text-xs text-[hsl(var(--muted-foreground))]">
              Looked at {result.selected_agents.map(agentLabel).join(", ")}
            </p>
          ) : null}
        </CardContent>
      </Card>
      {result.findings.length > 0 ? (
        <section className="grid gap-3" aria-label="Key findings">
          <h2 className="text-sm font-medium">Key findings</h2>
          {result.findings.map((item) => (
            <Card key={item.id}>
              <CardHeader>
                <CardTitle>{item.title}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm">
                <p>{item.description}</p>
                <EvidenceList ids={item.evidence_ids} evidence={result.evidence} />
              </CardContent>
            </Card>
          ))}
        </section>
      ) : null}
      {result.insights.length > 0 ? (
        <section className="grid gap-3" aria-label="Insights">
          <h2 className="text-sm font-medium">What it may mean</h2>
          {result.insights.map((item) => (
            <Card key={item.id}>
              <CardHeader>
                <CardTitle>{item.title}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm">
                <p>{item.description}</p>
                <EvidenceList ids={item.evidence_ids} evidence={result.evidence} />
              </CardContent>
            </Card>
          ))}
        </section>
      ) : null}
      {result.contradictions.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Conflicting signals</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            {result.contradictions.map((item) => (
              <p key={item.id}>
                {item.left_fact} versus {item.right_fact}
              </p>
            ))}
          </CardContent>
        </Card>
      ) : null}
      {result.recommendations.length > 0 ? (
        <section className="grid gap-3" aria-label="Recommendations">
          <h2 className="text-sm font-medium">Recommendations</h2>
          {result.recommendations.map((item) => (
            <Card key={item.id}>
              <CardHeader>
                <CardTitle>{item.title}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm">
                <p>{item.recommendation}</p>
                <p className="text-[hsl(var(--muted-foreground))]">{item.rationale}</p>
                {item.expected_objective ? (
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Goal: {item.expected_objective}
                  </p>
                ) : null}
                <EvidenceList ids={item.evidence_ids} evidence={result.evidence} />
                {item.limitations.length > 0 ? (
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Limits: {item.limitations.join(" · ")}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </section>
      ) : null}
      {result.limitations.length > 0 ? (
        <p className="text-sm text-[hsl(var(--muted-foreground))]">
          Limits: {result.limitations.join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

export function AskView() {
  const session = useSessionStore();
  const client = useQueryClient();
  const [question, setQuestion] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const history = useQuery({
    queryKey: ["intelligence-list", session.data?.store_id],
    queryFn: listIntelligence,
    enabled: Boolean(session.data?.store_id),
  });
  const active = useQuery({
    queryKey: ["intelligence-run", activeId],
    queryFn: () => fetchIntelligence(activeId as string),
    enabled: Boolean(activeId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "PENDING" || status === "RUNNING" ? 1500 : false;
    },
  });
  const ask = useMutation({
    mutationFn: startIntelligence,
    onSuccess: (run) => {
      setActiveId(run.run_id);
      void client.invalidateQueries({ queryKey: ["intelligence-list"] });
    },
  });
  if (session.isLoading) return <LoadingBoard />;
  if (session.isError && isAuthError(session.error)) return <ConnectStoreBoard />;
  if (session.isError) return <ErrorBoard message={(session.error as Error).message} />;

  const submit = (value: string) => {
    const cleaned = value.trim();
    if (!cleaned) return;
    setQuestion(cleaned);
    ask.mutate(cleaned);
  };

  return (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <h1 className="text-xl font-semibold tracking-tight">Ask MerchantOS</h1>
        <p className="max-w-2xl text-sm text-[hsl(var(--muted-foreground))]">
          Ask a business question. MerchantOS reads your store data, explains what it found, and
          can recommend a change. It cannot update Shopify until you approve it.
        </p>
      </div>
      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          submit(question);
        }}
      >
        <label className="grid gap-2" htmlFor="merchant-question">
          <span className="text-sm font-medium">Your question</span>
          <textarea
            id="merchant-question"
            name="question"
            rows={3}
            maxLength={4000}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="How can I increase profit this month without increasing ad spend?"
            className="w-full rounded-md border bg-[hsl(var(--card))] px-3 py-2 text-sm"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((item) => (
            <Button key={item} type="button" variant="outline" size="sm" onClick={() => submit(item)}>
              {item}
            </Button>
          ))}
        </div>
        <div>
          <Button type="submit" disabled={ask.isPending || !question.trim()} aria-busy={ask.isPending}>
            {ask.isPending ? "Asking…" : "Ask"}
          </Button>
        </div>
      </form>
      {ask.isError ? <ErrorBoard message={(ask.error as Error).message} /> : null}
      {activeId && active.isLoading ? <LoadingBoard /> : null}
      {active.isError ? <ErrorBoard message={(active.error as Error).message} /> : null}
      {active.data ? (
        <article className="grid gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-medium">{active.data.question}</h2>
            <RunStatus status={active.data.status} />
          </div>
          {active.data.error_message ? (
            <ErrorBoard message={active.data.error_message} />
          ) : null}
          {active.data.result ? <Report result={active.data.result} /> : null}
          {!active.data.result && (active.data.status === "PENDING" || active.data.status === "RUNNING") ? (
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              Reading your store and preparing an answer…
            </p>
          ) : null}
        </article>
      ) : null}
      <section className="grid gap-3" aria-label="Recent questions">
        <h2 className="text-sm font-medium">Recent questions</h2>
        {(history.data?.runs ?? []).length === 0 ? (
          <EmptyBoard
            title="No questions yet"
            body="Ask how the store is doing, or why revenue moved. Answers include evidence you can open."
          />
        ) : (
          <ul className="grid gap-2">
            {(history.data?.runs ?? []).map((run: IntelligenceRun) => (
              <li key={run.run_id}>
                <button
                  type="button"
                  className="w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-[hsl(var(--muted))]"
                  onClick={() => setActiveId(run.run_id)}
                >
                  <span className="font-medium">{run.question}</span>
                  <span className="ml-2 text-[hsl(var(--muted-foreground))]">
                    {run.status === "COMPLETED" ? "Ready" : run.status === "FAILED" ? "Could not finish" : "Working…"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
