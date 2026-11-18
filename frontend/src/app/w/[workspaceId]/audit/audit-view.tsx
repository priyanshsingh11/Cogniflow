"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { EmptyState, ErrorNote, Icon, PageHeader, SkeletonRows } from "@/components/page-header";
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

  const tone = (a: string) =>
    /failed|deleted|rejected/.test(a) ? "text-fail" : /created|signup|login$|registered/.test(a) ? "text-ok" : "text-ink";

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader eyebrow="Admin · append-only" title={<>Audit <em>log</em></>}>
        A permanent record of sign-ins and every change in this workspace. Visible to admins.
      </PageHeader>

      <form
        className="rise mt-6 flex gap-2"
        style={{ "--d": "80ms" } as React.CSSProperties}
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
          className="w-full max-w-sm rounded-lg border border-line-strong bg-card px-3.5 py-2 font-mono text-[12.5px] text-ink outline-none placeholder:text-muted focus:border-signal"
        />
        <button type="submit" className="btn-ghost !py-2">Filter</button>
        {filter && (
          <button type="button" onClick={() => { setAction(""); setFilter(""); setOffset(0); }} className="px-2 text-[13px] text-muted hover:text-ink">
            Clear
          </button>
        )}
      </form>

      {error && <ErrorNote>{error}</ErrorNote>}
      {!rows && !error && <SkeletonRows />}
      {rows && rows.length === 0 && (
        <EmptyState icon={<Icon name="log" />} title={<>No <em>events</em></>}>
          {filter ? `Nothing recorded for "${filter}".` : "Events will appear here as people use the workspace."}
        </EmptyState>
      )}

      {rows && rows.length > 0 && (
        <ul className="relative mt-6 grid gap-2 border-l border-line-strong pl-5">
          {rows.map((r, i) => (
            <li key={r.id} className="step-in relative rounded-xl border border-line-strong bg-card px-4 py-3" style={{ animationDelay: `${Math.min(i, 10) * 30}ms` }}>
              <span className="absolute -left-[1.62rem] top-4 h-2 w-2 rounded-full border-2 border-paper bg-signal" aria-hidden="true" />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className={`font-mono text-[13px] font-medium ${tone(r.action)}`}>{r.action}</span>
                <span className="font-mono text-[11px] text-muted">{new Date(r.created_at).toLocaleString()}</span>
              </div>
              <p className="mt-1 text-[12.5px] text-muted">
                {r.actor_email ?? "system"}
                {r.entity_type ? ` · ${r.entity_type}` : ""}
                {r.entity_id ? ` ${r.entity_id.slice(0, 8)}` : ""}
              </p>
              {Object.keys(r.metadata).length > 0 && (
                <details className="mt-1.5">
                  <summary className="cursor-pointer font-mono text-[11px] text-muted hover:text-ink">details</summary>
                  <pre className="mt-1.5 overflow-x-auto rounded-lg bg-paper-2 p-3 font-mono text-[11.5px] leading-5 text-ink-2">
                    {JSON.stringify(r.metadata, null, 2)}
                  </pre>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-6 flex items-center gap-2">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="btn-ghost !py-1.5 disabled:opacity-40">← Newer</button>
        <button disabled={!rows || rows.length < PAGE} onClick={() => setOffset(offset + PAGE)} className="btn-ghost !py-1.5 disabled:opacity-40">Older →</button>
      </div>
    </div>
  );
}
