"use client";

import { useEffect, useState } from "react";
import { usePrefersReducedMotion } from "./use-in-view";

type Status = "pending" | "running" | "done" | "waiting";

const END = 12;

/** Which status each step has at timeline tick `t`. */
function statusAt(step: number, t: number): Status {
  const spans: [number, number, number][] = [
    // [startRunning, doneAt, _]
    [1, 2, 0],
    [3, 6, 0],
    [7, 10, 0], // waiting until 10
    [10, 11, 0],
  ];
  const [start, done] = spans[step];
  if (t >= done) return "done";
  if (t >= start) return step === 2 ? "waiting" : "running";
  return "pending";
}

const STEPS = [
  { type: "knowledge_search", name: "Search runbooks", out: "3 passages · 412 ms" },
  { type: "llm", name: "Draft triage summary", out: "1,284 tokens · 2.3 s" },
  { type: "approval", name: "Page the on-call lead", out: "approved by maya" },
  { type: "mcp_tool", name: "mcp__github__create_issue", out: "issue #214 · 640 ms" },
];

const RUN_STATUS: Record<string, { label: string; cls: string }> = {
  running: { label: "running", cls: "bg-info-soft text-info" },
  waiting: { label: "waiting approval", cls: "bg-wait-soft text-wait" },
  done: { label: "succeeded", cls: "bg-ok-soft text-ok" },
};

export function HeroTrace() {
  const reduced = usePrefersReducedMotion();
  const [tick, setT] = useState(0);
  const t = reduced ? END : tick;

  useEffect(() => {
    if (reduced) return;
    let cur = 0;
    let timer: ReturnType<typeof setTimeout>;
    const next = () => {
      cur = cur >= END + 3 ? 0 : cur + 1;
      setT(Math.min(cur, END));
      timer = setTimeout(next, cur === END ? 3200 : cur === 0 ? 700 : 850);
    };
    timer = setTimeout(next, 900);
    return () => clearTimeout(timer);
  }, [reduced]);

  const statuses = STEPS.map((_, i) => statusAt(i, t));
  const runState = statuses.every((s) => s === "done")
    ? "done"
    : statuses.includes("waiting")
      ? "waiting"
      : "running";
  const tokens = t < 3 ? 0 : t < 6 ? 640 : 1284;
  const fallback = t >= 4 && t < 6;
  const rs = RUN_STATUS[runState];

  return (
    <div className="relative">
      <div
        className="absolute -inset-px rounded-[1.4rem] opacity-70 blur-2xl"
        style={{ background: "radial-gradient(60% 60% at 70% 20%, color-mix(in srgb, var(--signal) 35%, transparent), transparent 70%)" }}
        aria-hidden="true"
      />
      <div className="relative overflow-hidden rounded-2xl border border-line-strong bg-card shadow-[0_30px_80px_-30px_rgba(22,20,15,0.35)]">
        {/* window chrome */}
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-line-strong" />
            <span className="h-2.5 w-2.5 rounded-full bg-line-strong" />
            <span className="h-2.5 w-2.5 rounded-full bg-line-strong" />
            <span className="ml-3 font-mono text-[11px] text-muted">run_8f3a · incident-triage v4</span>
          </div>
          <span className={`rounded-full px-2.5 py-0.5 font-mono text-[10.5px] transition-colors duration-300 ${rs.cls}`}>
            {rs.label}
          </span>
        </div>

        {/* steps */}
        <ol className="relative px-4 py-5 sm:px-5">
          <span className="absolute bottom-9 left-[2.15rem] top-9 w-px bg-line sm:left-[2.4rem]" aria-hidden="true" />
          {STEPS.map((s, i) => {
            const st = statuses[i];
            const active = st === "running" || st === "waiting";
            return (
              <li key={s.type} className="relative flex gap-3.5 pb-4 last:pb-0">
                <span
                  className={`relative z-10 mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full border text-[11px] font-semibold transition-all duration-300 ${
                    st === "done"
                      ? "border-ok bg-ok text-white"
                      : st === "waiting"
                        ? "border-wait bg-wait-soft text-wait"
                        : st === "running"
                          ? "border-signal bg-signal-soft text-signal"
                          : "border-line-strong bg-card text-muted"
                  }`}
                >
                  {st === "done" ? (
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2.5 6.2l2.4 2.4 4.6-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  ) : (
                    i + 1
                  )}
                  {active && (
                    <span className={`pulse-dot absolute inset-0 rounded-full ${st === "waiting" ? "text-wait" : "text-signal"}`} />
                  )}
                </span>

                <div className={`min-w-0 flex-1 rounded-xl border px-3.5 py-2.5 transition-all duration-300 ${
                  active ? "border-line-strong bg-paper shadow-sm" : "border-transparent"
                }`}>
                  <div className="flex items-baseline justify-between gap-3">
                    <p className={`truncate text-[13.5px] font-medium transition-colors ${st === "pending" ? "text-muted" : "text-ink"}`}>
                      {s.name}
                    </p>
                    <span className="shrink-0 font-mono text-[10.5px] text-muted">{s.type}</span>
                  </div>
                  <div className="mt-0.5 h-4 font-mono text-[11px] text-muted">
                    {st === "done" && <span className="step-in text-ok">{s.out}</span>}
                    {st === "running" && i === 1 && fallback && (
                      <span className="step-in text-wait">429 on groq → fell back to openrouter</span>
                    )}
                    {st === "running" && !(i === 1 && fallback) && (
                      <span className="caret text-signal">executing</span>
                    )}
                    {st === "waiting" && <span className="text-wait">paused — waiting for a human</span>}
                  </div>
                  {active && st === "running" && <div className="shimmer mt-2 h-px w-full" />}
                </div>
              </li>
            );
          })}
        </ol>

        {/* footer stats */}
        <div className="grid grid-cols-3 divide-x divide-line border-t border-line bg-paper-2/50 text-center">
          {[
            ["tier", "medium"],
            ["tokens", tokens.toLocaleString()],
            ["attempts", t < 4 ? (t < 3 ? "—" : "1") : "2"],
          ].map(([k, v]) => (
            <div key={k} className="px-3 py-2.5">
              <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{k}</p>
              <p className="mt-0.5 font-mono text-[13px] font-medium tabular-nums text-ink">{v}</p>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-3 text-center font-mono text-[10.5px] text-muted">Simulated run · same steps the product records</p>
    </div>
  );
}
