"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge, isActiveRun } from "@/components/status-badge";
import { ApiError, cancelRun, getRun } from "@/lib/api";
import type { StepRun, WorkflowRun } from "@/types";

const POLL_MS = 2000;

function duration(start: string | null, end: string | null): string {
  if (!start) return "–";
  const ms = (end ? new Date(end).getTime() : Date.now()) - new Date(start).getTime();
  return ms < 1000 ? `${Math.max(ms, 0)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-72 overflow-auto rounded bg-zinc-100 p-2 text-xs text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function StepRunCard({ step }: { step: StepRun }) {
  return (
    <details className="rounded-md border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3">
        <span className="min-w-0 truncate text-sm font-medium text-black dark:text-zinc-100">{step.step_name}</span>
        <span className="flex shrink-0 items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
          {step.finished_at ? duration(step.started_at, step.finished_at) : null}
          {step.attempt > 1 && <span>attempt {step.attempt}</span>}
          <StatusBadge status={step.status} />
        </span>
      </summary>
      <div className="grid gap-3 border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
        {step.error && <p className="text-sm text-red-600 dark:text-red-400">{step.error}</p>}
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {step.llm_calls_count} model {step.llm_calls_count === 1 ? "call" : "calls"} ·{" "}
          {step.tool_calls_count} tool {step.tool_calls_count === 1 ? "call" : "calls"}
        </p>
        {step.input && (
          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Input</p>
            <Json value={step.input} />
          </div>
        )}
        {step.output && (
          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Output</p>
            <Json value={step.output} />
          </div>
        )}
      </div>
    </details>
  );
}

export function RunDetailView() {
  const { workspaceId, runId } = useParams<{ workspaceId: string; runId: string }>();
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getRun(workspaceId, runId)
      .then((r) => !cancelled && setRun(r))
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the run");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, runId, tick]);

  // Poll while the run is moving, and while it waits for a person (so an approval elsewhere shows up).
  const polling = run ? isActiveRun(run.status) || run.status === "waiting_approval" : false;
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => setTick((n) => n + 1), POLL_MS);
    return () => clearInterval(timer);
  }, [polling]);

  async function cancel() {
    setCancelling(true);
    try {
      setRun(await cancelRun(workspaceId, runId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not cancel the run");
    } finally {
      setCancelling(false);
    }
  }

  if (error && !run) return <p className="text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!run) return <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>;

  const cancellable = run.status === "queued" || run.status === "running" || run.status === "waiting_approval";
  return (
    <div className="mx-auto w-full max-w-3xl">
      <Link href={`/w/${workspaceId}/runs`} className="text-sm text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-100">
        ← Runs
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-xl font-semibold text-black dark:text-zinc-50">{run.id.slice(0, 8)}</h1>
          <StatusBadge status={run.status} />
        </div>
        <div className="flex items-center gap-2">
          <Link href={`/w/${workspaceId}/workflows/${run.workflow_id}`} className="text-sm text-zinc-600 hover:underline dark:text-zinc-300">
            Open workflow
          </Link>
          {cancellable && (
            <button onClick={() => void cancel()} disabled={cancelling} className="rounded-md border border-zinc-300 px-3 py-1 text-sm text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900">
              {cancelling ? "Cancelling…" : "Cancel run"}
            </button>
          )}
        </div>
      </div>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        Started {run.started_at ? new Date(run.started_at).toLocaleString() : "not yet"}
        {run.finished_at && ` · took ${duration(run.started_at, run.finished_at)}`}
      </p>

      {run.status === "waiting_approval" && (
        <p className="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          This run is paused for a human decision.{" "}
          <Link href={`/w/${workspaceId}/approvals`} className="font-medium underline">
            Open the approval inbox
          </Link>
        </p>
      )}
      {run.error && <p role="alert" className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-300">{run.error}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <h2 className="mt-8 text-sm font-semibold uppercase tracking-widest text-zinc-500 dark:text-zinc-400">Input</h2>
      <div className="mt-2"><Json value={run.input} /></div>

      <h2 className="mt-8 text-sm font-semibold uppercase tracking-widest text-zinc-500 dark:text-zinc-400">Steps</h2>
      <div className="mt-2 grid gap-2">
        {run.step_runs.length === 0 && <p className="text-sm text-zinc-500 dark:text-zinc-400">No steps have started yet.</p>}
        {run.step_runs.map((s) => <StepRunCard key={s.id} step={s} />)}
      </div>

      {run.output && (
        <>
          <h2 className="mt-8 text-sm font-semibold uppercase tracking-widest text-zinc-500 dark:text-zinc-400">Run output</h2>
          <div className="mt-2"><Json value={run.output} /></div>
        </>
      )}
    </div>
  );
}
