"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge, isActiveRun } from "@/components/status-badge";
import { ApiError, listRuns } from "@/lib/api";
import type { WorkflowRun } from "@/types";

const POLL_MS = 3000;

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

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">Runs</h1>
      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">Every execution of every workflow, newest first.</p>
      {error && <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {runs === null && !error && <p className="mt-8 text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}
      {runs?.length === 0 && (
        <p className="mt-8 rounded-md border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
          No runs yet. Open a workflow and press Run.
        </p>
      )}
      <ul className="mt-6 grid gap-2">
        {runs?.map((r) => (
          <li key={r.id}>
            <Link
              href={`/w/${workspaceId}/runs/${r.id}`}
              className="flex items-center justify-between gap-3 rounded-md border border-zinc-200 bg-white px-4 py-3 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800"
            >
              <div className="min-w-0">
                <p className="truncate font-mono text-xs text-zinc-500 dark:text-zinc-400">{r.id.slice(0, 8)}</p>
                <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                  {new Date(r.created_at).toLocaleString()} · {r.step_runs.length} step runs
                </p>
                {r.error && <p className="mt-1 truncate text-xs text-red-600 dark:text-red-400">{r.error}</p>}
              </div>
              <StatusBadge status={r.status} />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
