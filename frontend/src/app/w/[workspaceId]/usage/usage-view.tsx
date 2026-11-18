"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, getUsage } from "@/lib/api";
import type { UsageReport } from "@/types";

const RANGES = [1, 7, 30, 90];

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
const num = (n: number) => n.toLocaleString();
const ms = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)} s` : `${Math.round(n)} ms`);

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-1 text-xl font-semibold text-black dark:text-zinc-50">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{hint}</p>}
    </div>
  );
}

function Table({ title, head, rows }: { title: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold text-black dark:text-zinc-50">{title}</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No data in this range.</p>
      ) : (
        <div className="mt-2 overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
              <tr>
                {head.map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="text-zinc-800 dark:text-zinc-200">
              {rows.map((row, i) => (
                <tr key={i} className="border-t border-zinc-200 dark:border-zinc-800">
                  {row.map((cell, j) => (
                    <td key={j} className="px-3 py-2">
                      {cell}
                    </td>
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
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">Usage</h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Model calls, tokens, reliability and slow spots for this workspace.
          </p>
        </div>
        <div role="group" aria-label="Time range" className="flex gap-1">
          {RANGES.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              aria-pressed={days === d}
              className={`rounded-md px-3 py-1 text-sm ${
                days === d
                  ? "bg-black font-medium text-white dark:bg-zinc-50 dark:text-black"
                  : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
              }`}
            >
              {d === 1 ? "24 h" : `${d} d`}
            </button>
          ))}
        </div>
      </div>

      {error && <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {!report && !error && <p className="mt-8 text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}

      {report && t && (
        <>
          <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="Model calls" value={num(t.llm_calls)} hint={`${num(t.llm_attempts)} attempts`} />
            <Tile
              label="Tokens"
              value={num(t.total_tokens)}
              hint={`${num(t.prompt_tokens)} in · ${num(t.completion_tokens)} out`}
            />
            <Tile label="Cost" value={`$${t.cost_usd.toFixed(4)}`} hint="free models cost $0" />
            <Tile label="Latency (p95)" value={ms(t.p95_latency_ms)} hint={`avg ${ms(t.avg_latency_ms)}`} />
            <Tile label="Fallback rate" value={pct(t.fallback_rate)} hint={`${t.fallback_calls} calls`} />
            <Tile label="Failure rate" value={pct(t.failure_rate)} hint={`${t.failed_calls} calls`} />
            <Tile
              label="Tool calls"
              value={num(t.tool_calls)}
              hint={`${t.tool_call_errors} errors`}
            />
            <Tile
              label="Run success"
              value={pct(t.run_success_rate)}
              hint={`${t.runs_succeeded}/${t.runs} runs, ${t.runs_failed} failed`}
            />
          </div>

          <section className="mt-8">
            <h2 className="text-sm font-semibold text-black dark:text-zinc-50">Attempts per day</h2>
            <div
              className="mt-2 flex h-28 items-end gap-0.5 rounded-md border border-zinc-200 p-2 dark:border-zinc-800"
              role="img"
              aria-label="Model attempts per day"
            >
              {report.by_day.map((d) => (
                <div
                  key={d.day}
                  title={`${d.day}: ${d.attempts} attempts, ${d.errors} errors, ${num(d.tokens)} tokens`}
                  className="flex h-full min-w-0 flex-1 flex-col justify-end"
                >
                  <div
                    className="w-full rounded-sm bg-sky-500"
                    style={{ height: `${(d.attempts / maxCalls) * 100}%`, minHeight: d.attempts ? 2 : 0 }}
                  />
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

          <section className="mt-8">
            <h2 className="text-sm font-semibold text-black dark:text-zinc-50">Slowest steps</h2>
            {report.slowest_steps.length === 0 ? (
              <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No data in this range.</p>
            ) : (
              <ul className="mt-2 grid gap-2">
                {report.slowest_steps.map((s) => (
                  <li key={s.step_run_id}>
                    <Link
                      href={`/w/${workspaceId}/runs/${s.workflow_run_id}`}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
                    >
                      <span className="text-zinc-800 dark:text-zinc-200">
                        {s.workflow_name} · {s.step_name}
                      </span>
                      <span className="flex items-center gap-2">
                        <StatusBadge status={s.status} />
                        <span className="text-zinc-500 dark:text-zinc-400">{ms(s.duration_ms)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-8">
            <h2 className="text-sm font-semibold text-black dark:text-zinc-50">Recent errors</h2>
            {report.recent_errors.length === 0 ? (
              <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No errors in this range.</p>
            ) : (
              <ul className="mt-2 grid gap-2">
                {report.recent_errors.map((e, i) => (
                  <li key={i} className="rounded-md border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800">
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      {e.kind === "run" ? "Workflow run" : "Model call"} · {new Date(e.created_at).toLocaleString()}
                    </p>
                    <p className="mt-0.5 break-words text-zinc-800 dark:text-zinc-200">{e.message}</p>
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
