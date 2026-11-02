"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, decideApproval, listApprovals } from "@/lib/api";
import type { Approval } from "@/types";

const POLL_MS = 4000;

/** The API echoes the description into details when a step gives none; hide that noise. */
function hasDetails(a: Approval): boolean {
  if (!a.details) return false;
  const rest = Object.entries(a.details).filter(
    ([key, value]) =>
      !(key === "description") &&
      !(key === "details" && typeof value === "object" && Object.keys(value ?? {}).length === 0),
  );
  return rest.length > 0;
}

export function ApprovalsView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [approvals, setApprovals] = useState<Approval[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listApprovals(workspaceId)
      .then((list) => !cancelled && setApprovals(list))
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load approvals");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, tick]);

  // New requests appear while runs execute in the background.
  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), POLL_MS);
    return () => clearInterval(timer);
  }, []);

  async function decide(approval: Approval, action: "approve" | "reject") {
    setBusy(approval.id);
    setError(null);
    try {
      await decideApproval(workspaceId, approval.id, action, reasons[approval.id]);
      setTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record the decision");
    } finally {
      setBusy(null);
    }
  }

  const pending = approvals?.filter((a) => a.status === "pending") ?? [];
  const decided = approvals?.filter((a) => a.status !== "pending") ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">Approvals</h1>
      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
        Runs pause here before sensitive steps. Approve to resume, reject to stop the run.
      </p>
      {error && <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {approvals === null && !error && <p className="mt-8 text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}

      {approvals && pending.length === 0 && (
        <p className="mt-8 rounded-md border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
          Nothing waiting for you.
        </p>
      )}
      <ul className="mt-6 grid gap-3">
        {pending.map((a) => (
          <li key={a.id} className="rounded-md border border-amber-300 bg-white p-4 dark:border-amber-800 dark:bg-zinc-900">
            <p className="text-sm font-medium text-black dark:text-zinc-100">{a.description ?? "Approval requested"}</p>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              Requested {new Date(a.requested_at).toLocaleString()}
              {a.workflow_run_id && (
                <>
                  {" · "}
                  <Link href={`/w/${workspaceId}/runs/${a.workflow_run_id}`} className="underline">view run</Link>
                </>
              )}
            </p>
            {hasDetails(a) && (
              <pre className="mt-3 max-h-48 overflow-auto rounded bg-zinc-100 p-2 text-xs text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
                {JSON.stringify(a.details, null, 2)}
              </pre>
            )}
            <input
              value={reasons[a.id] ?? ""}
              onChange={(e) => setReasons((r) => ({ ...r, [a.id]: e.target.value }))}
              placeholder="Reason (optional)"
              className="mt-3 w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-black outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
            />
            <div className="mt-3 flex gap-2">
              <button onClick={() => void decide(a, "approve")} disabled={busy === a.id} className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
                Approve
              </button>
              <button onClick={() => void decide(a, "reject")} disabled={busy === a.id} className="rounded-md border border-red-300 px-4 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950">
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>

      {decided.length > 0 && (
        <>
          <h2 className="mt-10 text-sm font-semibold uppercase tracking-widest text-zinc-500 dark:text-zinc-400">History</h2>
          <ul className="mt-3 grid gap-2">
            {decided.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 rounded-md border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
                <div className="min-w-0">
                  <p className="truncate text-sm text-black dark:text-zinc-100">{a.description ?? "Approval"}</p>
                  <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                    {a.decided_at ? new Date(a.decided_at).toLocaleString() : ""}
                    {a.reason ? ` · ${a.reason}` : ""}
                  </p>
                </div>
                <StatusBadge status={a.status} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
