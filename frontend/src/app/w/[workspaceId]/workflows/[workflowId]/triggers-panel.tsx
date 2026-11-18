"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorNote } from "@/components/page-header";
import {
  API_BASE_URL,
  ApiError,
  createTrigger,
  deleteTrigger,
  listTriggers,
  rotateTrigger,
  updateTrigger,
} from "@/lib/api";
import { useWorkspace } from "@/lib/use-role";
import type { WorkflowTrigger } from "@/types";

const field =
  "w-full rounded-lg border border-line-strong bg-paper px-3.5 py-2 text-[13.5px] text-ink outline-none placeholder:text-muted focus:border-signal";

const PRESETS: [string, string][] = [
  ["Every hour", "0 * * * *"],
  ["Every day 09:00", "0 9 * * *"],
  ["Weekdays 09:00", "0 9 * * 1-5"],
  ["Every Monday 09:00", "0 9 * * 1"],
];

function msg(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : fallback;
}
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "—");

export function TriggersPanel({ workspaceId, workflowId }: { workspaceId: string; workflowId: string }) {
  const { isAdmin } = useWorkspace(workspaceId);
  const [triggers, setTriggers] = useState<WorkflowTrigger[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<"schedule" | "webhook" | null>(null);
  const [cron, setCron] = useState("0 9 * * 1-5");
  const [tz, setTz] = useState("UTC");
  const [input, setInput] = useState("{}");
  // Secrets are only returned once; keep them in memory until the page closes.
  const [secrets, setSecrets] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    listTriggers(workspaceId, workflowId)
      .then(setTriggers)
      .catch((e) => setError(msg(e, "Could not load triggers")));
  }, [workspaceId, workflowId]);
  useEffect(load, [load]);

  async function run(fn: () => Promise<unknown>, fallback: string) {
    setError(null);
    try {
      await fn();
      load();
    } catch (e) {
      setError(msg(e, fallback));
    }
  }

  async function create() {
    if (!adding) return;
    setError(null);
    try {
      let parsed: Record<string, unknown> = {};
      if (adding === "schedule") {
        parsed = JSON.parse(input || "{}") as Record<string, unknown>;
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error("input");
      }
      const created = await createTrigger(workspaceId, workflowId, {
        type: adding,
        ...(adding === "schedule" ? { cron, timezone: tz, input: parsed } : {}),
      });
      if (created.secret) setSecrets((s) => ({ ...s, [created.id]: created.secret as string }));
      setAdding(null);
      load();
    } catch (e) {
      setError(e instanceof SyntaxError || (e instanceof Error && e.message === "input")
        ? "Input must be a JSON object." : msg(e, "Could not create the trigger"));
    }
  }

  return (
    <section className="mt-6 rounded-2xl border border-line-strong bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Triggers</p>
          <p className="mt-1 text-[13px] text-muted">Start this workflow automatically on a schedule, or when another system calls a URL.</p>
        </div>
        {isAdmin && (
          <div className="flex gap-2">
            <button className="btn-ghost !px-3 !py-1.5 text-[13px]" onClick={() => setAdding("schedule")}>+ Schedule</button>
            <button className="btn-ghost !px-3 !py-1.5 text-[13px]" onClick={() => setAdding("webhook")}>+ Webhook</button>
          </div>
        )}
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}

      {adding && (
        <div className="rise mt-4 grid gap-3 rounded-xl border border-signal/40 bg-paper p-4">
          {adding === "schedule" ? (
            <>
              <div className="flex flex-wrap gap-1.5">
                {PRESETS.map(([label, expr]) => (
                  <button key={expr} type="button" onClick={() => setCron(expr)} className={`rounded-full border px-3 py-1 font-mono text-[11px] ${cron === expr ? "border-signal text-signal" : "border-line text-ink-2"}`}>{label}</button>
                ))}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <input className={`${field} font-mono`} value={cron} onChange={(e) => setCron(e.target.value)} placeholder="minute hour day month weekday" />
                <input className={field} value={tz} onChange={(e) => setTz(e.target.value)} placeholder="Timezone, e.g. Asia/Kolkata" />
              </div>
              <textarea rows={2} spellCheck={false} className={`${field} font-mono`} value={input} onChange={(e) => setInput(e.target.value)} placeholder='Run input (JSON), e.g. {"topic": "daily summary"}' />
            </>
          ) : (
            <p className="text-[13px] text-ink-2">You get a secret URL once. Anything POSTed to it as JSON becomes the run input.</p>
          )}
          <div className="flex gap-2">
            <button className="btn-primary" onClick={() => void create()}>Create {adding}</button>
            <button className="btn-ghost" onClick={() => setAdding(null)}>Cancel</button>
          </div>
        </div>
      )}

      {triggers.length === 0 && !adding && <p className="mt-4 text-[13px] text-muted">No triggers yet. This workflow only runs when someone starts it.</p>}
      <ul className="mt-4 grid gap-3">
        {triggers.map((t) => {
          const secret = secrets[t.id];
          const url = secret ? `${API_BASE_URL}/hooks/${secret}` : null;
          return (
            <li key={t.id} className="rounded-xl border border-line bg-paper p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-[14px] font-medium">
                    <span className="rounded-full bg-signal-soft px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-signal">{t.type}</span>
                    {t.type === "schedule" ? <span className="font-mono text-[12.5px]">{t.cron} · {t.timezone}</span> : <span className="font-mono text-[12.5px]">/hooks/{t.secret_prefix}…</span>}
                    {!t.enabled && <span className="text-[12px] text-muted">(paused)</span>}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-muted">
                    {t.type === "schedule" && t.enabled ? `next ${when(t.next_run_at)} · ` : ""}last fired {when(t.last_run_at)}
                  </p>
                </div>
                {isAdmin && (
                  <div className="flex gap-2 text-[12.5px]">
                    <button className="btn-ghost !px-3 !py-1" onClick={() => void run(() => updateTrigger(workspaceId, workflowId, t.id, { enabled: !t.enabled }), "Could not update")}>{t.enabled ? "Pause" : "Resume"}</button>
                    {t.type === "webhook" && (
                      <button className="btn-ghost !px-3 !py-1" onClick={() => void run(async () => {
                        if (!confirm("Rotate the secret? The old URL stops working immediately.")) return;
                        const r = await rotateTrigger(workspaceId, workflowId, t.id);
                        if (r.secret) setSecrets((s) => ({ ...s, [t.id]: r.secret as string }));
                      }, "Could not rotate")}>Rotate</button>
                    )}
                    <button className="btn-ghost !px-3 !py-1 !text-fail" onClick={() => confirm("Delete this trigger?") && void run(() => deleteTrigger(workspaceId, workflowId, t.id), "Could not delete")}>Delete</button>
                  </div>
                )}
              </div>
              {url && (
                <div className="mt-3 rounded-lg border border-ok/40 bg-ok-soft p-3">
                  <p className="text-[12px] text-ok">Copy this URL now. It will not be shown again.</p>
                  <code className="mt-1 block break-all font-mono text-[12px] text-ink">{url}</code>
                  <button className="btn-ghost mt-2 !px-3 !py-1 text-[12px]" onClick={() => void navigator.clipboard.writeText(url)}>Copy</button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
