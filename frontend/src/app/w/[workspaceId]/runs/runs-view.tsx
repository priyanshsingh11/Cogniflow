"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { EmptyState, ErrorNote, Icon, PageHeader, SkeletonRows, Stat } from "@/components/page-header";
import { StatusBadge, isActiveRun } from "@/components/status-badge";
import { ApiError, listRuns } from "@/lib/api";
import type { WorkflowRun } from "@/types";

const POLL_MS = 3000;

const BLOCK: Record<string, string> = {
  succeeded: "bg-ok",
  running: "bg-signal",
  failed: "bg-fail",
  waiting_approval: "bg-wait",
};

function duration(r: WorkflowRun): string | null {
  if (!r.started_at || !r.finished_at) return null;
  const ms = new Date(r.finished_at).getTime() - new Date(r.started_at).getTime();
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

export function RunsView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [runs, setRuns] = useState<WorkflowRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listRuns(workspaceId)
      .then((list) => !cancelled && setRuns(list))
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load runs");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, tick]);

  // Keep refreshing while something is still queued or running.
  const anyActive = runs?.some((r) => isActiveRun(r.status)) ?? false;
  useEffect(() => {
    if (!anyActive) return;
    const timer = setInterval(() => setTick((n) => n + 1), POLL_MS);
    return () => clearInterval(timer);
  }, [anyActive]);

  const count = (st: string) => runs?.filter((r) => r.status === st).length ?? 0;

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader eyebrow="History" title={<>Every <em>run</em></>} action={
        anyActive ? (
          <span className="inline-flex items-center gap-2 rounded-full border border-line-strong bg-card px-3 py-1.5 font-mono text-[11px] text-ink-2">
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-signal text-signal" /> live · refreshing
          </span>
        ) : undefined
      }>
        Every execution of every workflow, newest first.
      </PageHeader>
      {error && <ErrorNote>{error}</ErrorNote>}
      {runs === null && !error && <SkeletonRows />}
      {runs?.length === 0 && (
        <EmptyState icon={<Icon name="run" />} title={<>Nothing has <em>run</em> yet</>}>
          Open a workflow and press Run. Each execution shows up here with every step recorded.
        </EmptyState>
      )}
      {runs && runs.length > 0 && (
        <div className="rise mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4" style={{ "--d": "80ms" } as React.CSSProperties}>
          <Stat label="Runs" value={runs.length} />
          <Stat label="Succeeded" value={count("succeeded")} tone="ok" />
          <Stat label="Failed" value={count("failed")} />
          <Stat label="Active" value={count("running") + count("queued") + count("waiting_approval")} tone="signal" />
        </div>
      )}
      <ul className="mt-6 grid gap-2">
        {runs?.map((r, i) => (
          <li key={r.id} className="step-in" style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}>
            <Link
              href={`/w/${workspaceId}/runs/${r.id}`}
              className="group flex items-center gap-4 rounded-xl border border-line-strong bg-card px-4 py-3.5 transition-colors hover:border-ink-2"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-[13px] font-medium text-ink">run_{r.id.slice(0, 8)}</span>
                  {duration(r) && <span className="font-mono text-[11px] text-muted">{duration(r)}</span>}
                </div>
                <p className="mt-0.5 font-mono text-[11px] text-muted">
                  {new Date(r.created_at).toLocaleString()} · {r.step_runs.length} step runs
                </p>
                {r.error && <p className="mt-1 truncate text-[12px] text-fail">{r.error}</p>}
                {r.step_runs.length > 0 && (
                  <div className="mt-2.5 flex gap-1" aria-hidden="true">
                    {r.step_runs.slice(0, 24).map((s) => (
                      <span key={s.id} className={`h-1.5 w-5 rounded-full ${BLOCK[s.status] ?? "bg-line-strong"} ${s.status === "running" ? "pulse-dot" : ""}`} />
                    ))}
                  </div>
                )}
              </div>
              <StatusBadge status={r.status} />
              <span className="font-mono text-[11px] text-muted transition-colors group-hover:text-signal">→</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
