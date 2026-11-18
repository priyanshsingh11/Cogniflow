"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, listAuditLogs } from "@/lib/api";
import type { AuditLog } from "@/types";

const PAGE = 50;

export function AuditView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [rows, setRows] = useState<AuditLog[] | null>(null);
  const [action, setAction] = useState("");
  const [filter, setFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listAuditLogs(workspaceId, { action: filter || undefined, limit: PAGE, offset })
      .then((list) => {
        if (cancelled) return;
        setRows(list);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the audit log");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, filter, offset]);

  return (
    <div className="mx-auto w-full max-w-4xl">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">Audit log</h1>
      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
        Append-only record of changes in this workspace. Visible to admins.
      </p>

      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setOffset(0);
          setFilter(action.trim());
        }}
      >
        <input
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder="Exact action, e.g. workflow.updated"
          aria-label="Filter by action"
          className="w-full max-w-xs rounded-md border border-zinc-300 bg-transparent px-3 py-1.5 text-sm dark:border-zinc-700"
        />
        <button type="submit" className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700">
          Filter
        </button>
      </form>

      {error && <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {!rows && !error && <p className="mt-8 text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}
      {rows && rows.length === 0 && (
        <p className="mt-8 rounded-md border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
          No events{filter ? ` for "${filter}"` : ""}.
        </p>
      )}

      {rows && rows.length > 0 && (
        <ul className="mt-4 grid gap-2">
          {rows.map((r) => (
            <li key={r.id} className="rounded-md border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-black dark:text-zinc-50">{r.action}</span>
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                  {new Date(r.created_at).toLocaleString()}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                {r.actor_email ?? "system"}
                {r.entity_type ? ` · ${r.entity_type}` : ""}
                {r.entity_id ? ` ${r.entity_id.slice(0, 8)}` : ""}
              </p>
              {Object.keys(r.metadata).length > 0 && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-zinc-500 dark:text-zinc-400">Details</summary>
                  <pre className="mt-1 overflow-x-auto rounded bg-zinc-50 p-2 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                    {JSON.stringify(r.metadata, null, 2)}
                  </pre>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex items-center gap-2">
        <button
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE))}
          className="rounded-md border border-zinc-300 px-3 py-1 text-sm disabled:opacity-40 dark:border-zinc-700"
        >
          Newer
        </button>
        <button
          disabled={!rows || rows.length < PAGE}
          onClick={() => setOffset(offset + PAGE)}
          className="rounded-md border border-zinc-300 px-3 py-1 text-sm disabled:opacity-40 dark:border-zinc-700"
        >
          Older
        </button>
      </div>
    </div>
  );
}
