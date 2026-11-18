"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { EmptyState, ErrorNote, Icon, PageHeader, SkeletonRows } from "@/components/page-header";
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
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader
        eyebrow="Human in the loop"
        title={<>Approval <em>inbox</em></>}
        action={
          pending.length > 0 ? (
            <span className="inline-flex items-center gap-2 rounded-full border border-wait/40 bg-wait-soft px-3 py-1.5 font-mono text-[11px] text-wait">
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-wait text-wait" /> {pending.length} waiting
            </span>
          ) : undefined
        }
      >
        Runs pause here before sensitive steps. Approve to resume, reject to stop the run.
      </PageHeader>
      {error && <ErrorNote>{error}</ErrorNote>}
      {approvals === null && !error && <SkeletonRows n={2} />}

      {approvals && pending.length === 0 && (
        <EmptyState icon={<Icon name="shield" />} title={<>All <em>clear</em></>}>
          Nothing is waiting for a decision. Paused runs will appear here.
        </EmptyState>
      )}
      <ul className="mt-6 grid gap-4">
        {pending.map((a) => (
          <li key={a.id} className="step-in relative overflow-hidden rounded-2xl border border-wait/50 bg-card p-5">
            <span className="absolute inset-y-0 left-0 w-1 bg-wait" aria-hidden="true" />
            <div className="flex flex-wrap items-start justify-between gap-3 pl-2">
              <div className="min-w-0">
                <p className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-wait">
                  <span className="pulse-dot h-2 w-2 rounded-full bg-wait text-wait" /> waiting approval
                </p>
                <p className="mt-2 text-[16px] font-medium tracking-tight text-ink">{a.description ?? "Approval requested"}</p>
                <p className="mt-1 font-mono text-[11px] text-muted">
                  Requested {new Date(a.requested_at).toLocaleString()}
                  {a.workflow_run_id && (
                    <>
                      {" · "}
                      <Link href={`/w/${workspaceId}/runs/${a.workflow_run_id}`} className="text-ink-2 underline decoration-signal underline-offset-4 hover:text-signal">view run</Link>
                    </>
                  )}
                </p>
              </div>
            </div>
            <div className="pl-2">
              {hasDetails(a) && (
                <pre className="mt-4 max-h-48 overflow-auto rounded-xl bg-paper-2 p-3 font-mono text-[11.5px] leading-5 text-ink-2">
                  {JSON.stringify(a.details, null, 2)}
                </pre>
              )}
              <input
                value={reasons[a.id] ?? ""}
                onChange={(e) => setReasons((r) => ({ ...r, [a.id]: e.target.value }))}
                placeholder="Reason (optional)"
                className="mt-4 w-full rounded-lg border border-line-strong bg-paper px-3.5 py-2 text-[13.5px] text-ink outline-none transition-shadow placeholder:text-muted focus:border-signal focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--signal)_20%,transparent)]"
              />
              <div className="mt-3 flex gap-2">
                <button onClick={() => void decide(a, "approve")} disabled={busy === a.id} className="rounded-lg bg-ok px-5 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50">
                  Approve &amp; resume
                </button>
                <button onClick={() => void decide(a, "reject")} disabled={busy === a.id} className="rounded-lg border border-fail/50 px-5 py-2 text-[13px] font-medium text-fail transition-colors hover:bg-fail-soft disabled:opacity-50">
                  Reject
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>

      {decided.length > 0 && (
        <>
          <h2 className="eyebrow mt-12">History</h2>
          <ul className="mt-3 grid gap-2">
            {decided.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 rounded-xl border border-line-strong bg-card px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-[14px] text-ink">{a.description ?? "Approval"}</p>
                  <p className="mt-0.5 font-mono text-[11px] text-muted">
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
