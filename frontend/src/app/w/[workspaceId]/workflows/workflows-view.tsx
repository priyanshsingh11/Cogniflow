"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, listWorkflows } from "@/lib/api";
import type { Workflow } from "@/types";

export function WorkflowsView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listWorkflows(workspaceId)
      .then((list) => !cancelled && setWorkflows(list))
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load workflows");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  return (
    <div className="mx-auto w-full max-w-3xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">Workflows</h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            A workflow is a saved list of steps. Run it any time and inspect every step afterwards.
          </p>
        </div>
        <Link
          href={`/w/${workspaceId}/workflows/new`}
          className="shrink-0 rounded-md bg-black px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
        >
          New workflow
        </Link>
      </div>
      {error && <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {workflows === null && !error && <p className="mt-8 text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}
      {workflows?.length === 0 && (
        <p className="mt-8 rounded-md border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
          No workflows yet. Create your first one.
        </p>
      )}
      <ul className="mt-6 grid gap-2">
        {workflows?.map((w) => (
          <li key={w.id}>
            <Link
              href={`/w/${workspaceId}/workflows/${w.id}`}
              className="flex items-center justify-between gap-3 rounded-md border border-zinc-200 bg-white px-4 py-3 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-black dark:text-zinc-100">{w.name}</p>
                {w.description && <p className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">{w.description}</p>}
              </div>
              <span className="shrink-0 text-xs text-zinc-500 dark:text-zinc-400">
                v{w.current_version?.version ?? "–"} · {w.current_version?.steps.length ?? 0} steps
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
