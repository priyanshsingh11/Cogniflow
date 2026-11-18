"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNote, PageHeader, SkeletonRows } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, getUsage } from "@/lib/api";
import type { UsageReport } from "@/types";

const RANGES = [1, 7, 30, 90];

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
const num = (n: number) => n.toLocaleString();
const ms = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)} s` : `${Math.round(n)} ms`);

function Tile({ label, value, hint, bad }: { label: string; value: string; hint?: string; bad?: boolean }) {
  return (
    <div className="rounded-xl border border-line bg-card px-4 py-3.5">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</p>
      <p className={`display mt-1.5 text-4xl leading-none tabular-nums ${bad ? "text-signal" : ""}`}>{value}</p>
      {hint && <p className="mt-1.5 font-mono text-[11px] text-muted">{hint}</p>}
    </div>
  );
}

function Table({ title, head, rows }: { title: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <section className="mt-10">
      <h2 className="eyebrow">{title}</h2>
      {rows.length === 0 ? (
        <p className="mt-3 text-[13px] text-muted">No data in this range.</p>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-xl border border-line-strong bg-card">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-paper-2/60 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted">
              <tr>
                {head.map((h) => (
                  <th key={h} className="px-4 py-2.5 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="text-ink-2">
              {rows.map((row, i) => (
                <tr key={i} className="border-t border-line transition-colors hover:bg-paper-2/40">
                  {row.map((cell, j) => (
                    <td key={j} className={`px-4 py-2.5 ${j === 0 ? "font-medium text-ink" : "font-mono text-[12px] tabular-nums"}`}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function UsageView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [days, setDays] = useState(7);
  const [report, setReport] = useState<UsageReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getUsage(workspaceId, days)
      .then((r) => {
        if (cancelled) return;
        setReport(r);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load usage");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, days]);

  const t = report?.totals;
  const maxCalls = Math.max(1, ...(report?.by_day.map((d) => d.attempts) ?? [1]));

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader
        eyebrow="Observability"
        title={<>Usage &amp; <em>reliability</em></>}
        action={
          <div role="group" aria-label="Time range" className="flex gap-0.5 rounded-lg border border-line-strong bg-card p-0.5">
            {RANGES.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                aria-pressed={days === d}
                className={`rounded-md px-3 py-1.5 font-mono text-[12px] transition-colors ${
                  days === d ? "bg-ink text-paper" : "text-ink-2 hover:bg-paper-2"
                }`}
              >
                {d === 1 ? "24h" : `${d}d`}
              </button>
            ))}
          </div>
        }
      >
        Model calls, tokens, reliability and slow spots for this workspace.
      </PageHeader>

      {error && <ErrorNote>{error}</ErrorNote>}
      {!report && !error && <SkeletonRows n={4} />}

      {report && t && (
        <>
          <div className="rise mt-6 grid grid-cols-2 gap-3 md:grid-cols-4" style={{ "--d": "60ms" } as React.CSSProperties}>
            <Tile label="Model calls" value={num(t.llm_calls)} hint={`${num(t.llm_attempts)} attempts`} />
            <Tile label="Tokens" value={num(t.total_tokens)} hint={`${num(t.prompt_tokens)} in · ${num(t.completion_tokens)} out`} />
            <Tile label="Cost" value={`$${t.cost_usd.toFixed(4)}`} hint="free models cost $0" />
            <Tile label="Latency p95" value={ms(t.p95_latency_ms)} hint={`avg ${ms(t.avg_latency_ms)}`} />
            <Tile label="Fallback rate" value={pct(t.fallback_rate)} hint={`${t.fallback_calls} calls`} />
            <Tile label="Failure rate" value={pct(t.failure_rate)} hint={`${t.failed_calls} calls`} bad={t.failure_rate > 0.05} />
            <Tile label="Tool calls" value={num(t.tool_calls)} hint={`${t.tool_call_errors} errors`} />
            <Tile label="Run success" value={pct(t.run_success_rate)} hint={`${t.runs_succeeded}/${t.runs} runs, ${t.runs_failed} failed`} />
          </div>

          <section className="mt-10">
            <div className="flex items-center justify-between">
              <h2 className="eyebrow">Attempts per day</h2>
              <span className="flex items-center gap-1.5 font-mono text-[11px] text-muted"><i className="inline-block h-2 w-2 rounded-sm bg-signal" /> errors</span>
            </div>
            <div className="mt-3 flex h-36 items-end gap-1 rounded-xl border border-line-strong bg-card p-3" role="img" aria-label="Model attempts per day">
              {report.by_day.map((d, i) => (
                <div
                  key={d.day}
                  title={`${d.day}: ${d.attempts} attempts, ${d.errors} errors, ${num(d.tokens)} tokens`}
                  className="flex h-full min-w-0 flex-1 flex-col justify-end"
                >
                  <div
                    className="bar-grow relative w-full overflow-hidden rounded-t-[3px] bg-ink/85"
                    style={{ height: `${(d.attempts / maxCalls) * 100}%`, minHeight: d.attempts ? 3 : 0, "--d": `${i * 25}ms` } as React.CSSProperties}
                  >
                    {d.errors > 0 && <div className="absolute inset-x-0 top-0 bg-signal" style={{ height: `${Math.max(8, (d.errors / d.attempts) * 100)}%` }} />}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <Table
            title="By tier"
            head={["Tier", "Calls", "Attempts", "Tokens", "Errors", "Avg latency"]}
            rows={report.by_tier.map((r) => [r.tier, r.calls, r.attempts, num(r.tokens), r.errors, ms(r.avg_latency_ms)])}
          />
          <Table
            title="By model"
            head={["Model", "Attempts", "Tokens", "Errors", "Avg latency"]}
            rows={report.by_model.map((r) => [`${r.provider}:${r.model}`, r.attempts, num(r.tokens), r.errors, ms(r.avg_latency_ms)])}
          />
          <Table
            title="By agent"
            head={["Agent", "Attempts", "Tokens", "Errors"]}
            rows={report.by_agent.map((r) => [r.agent_name ?? "(no agent)", r.attempts, num(r.tokens), r.errors])}
          />
          <Table
            title="Slowest workflows"
            head={["Workflow", "Runs", "Avg", "Max"]}
            rows={report.slowest_workflows.map((r) => [r.workflow_name, r.runs, ms(r.avg_duration_ms), ms(r.max_duration_ms)])}
          />

          <section className="mt-10">
            <h2 className="eyebrow">Slowest steps</h2>
            {report.slowest_steps.length === 0 ? (
              <p className="mt-3 text-[13px] text-muted">No data in this range.</p>
            ) : (
              <ul className="mt-3 grid gap-2">
                {report.slowest_steps.map((s) => (
                  <li key={s.step_run_id}>
                    <Link
                      href={`/w/${workspaceId}/runs/${s.workflow_run_id}`}
                      className="group flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line-strong bg-card px-4 py-2.5 text-[13px] transition-colors hover:border-ink-2"
                    >
                      <span className="text-ink">{s.workflow_name} <span className="text-muted">·</span> {s.step_name}</span>
                      <span className="flex items-center gap-3">
                        <StatusBadge status={s.status} />
                        <span className="font-mono text-[12px] text-muted">{ms(s.duration_ms)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-10">
            <h2 className="eyebrow">Recent errors</h2>
            {report.recent_errors.length === 0 ? (
              <p className="mt-3 flex items-center gap-2 text-[13px] text-ok"><span className="h-1.5 w-1.5 rounded-full bg-ok" /> No errors in this range.</p>
            ) : (
              <ul className="mt-3 grid gap-2">
                {report.recent_errors.map((e, i) => (
                  <li key={i} className="rounded-xl border border-fail/30 bg-fail-soft/40 px-4 py-3 text-[13px]">
                    <p className="font-mono text-[11px] text-fail">
                      {e.kind === "run" ? "workflow run" : "model call"} · {new Date(e.created_at).toLocaleString()}
                    </p>
                    <p className="mt-1 break-words text-ink-2">{e.message}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
