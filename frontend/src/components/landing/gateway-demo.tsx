"use client";

import { useEffect, useState } from "react";
import { useInView, usePrefersReducedMotion } from "./use-in-view";

const ATTEMPTS = [
  { model: "groq:openai/gpt-oss-20b", tier: 0, result: "429 rate limited", action: "next model · no retry", kind: "fail" },
  { model: "openrouter:google/gemma-4-26b-a4b-it:free", tier: 0, result: "timeout", action: "retry once with backoff, then next", kind: "fail" },
  { model: "openrouter:liquid/lfm-2.5-2.6b:free", tier: 0, result: "200 · empty output", action: "quality miss → escalate a tier up", kind: "warn" },
  { model: "groq:qwen/qwen3.8-27b", tier: 1, result: "200 · valid", action: "answer returned", kind: "ok" },
] as const;

const TIERS = ["small", "medium", "large"];

export function GatewayDemo() {
  const [ref, seen] = useInView<HTMLDivElement>(0.3);
  const reduced = usePrefersReducedMotion();
  const [step, setN] = useState(0);
  const n = reduced ? ATTEMPTS.length : step;

  useEffect(() => {
    if (!seen || reduced) return;
    let cur = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      cur = cur >= ATTEMPTS.length + 2 ? 0 : cur + 1;
      setN(Math.min(cur, ATTEMPTS.length));
      timer = setTimeout(tick, cur >= ATTEMPTS.length ? 3200 : 1250);
    };
    timer = setTimeout(tick, 400);
    return () => clearTimeout(timer);
  }, [seen, reduced]);

  const current = n === 0 ? 0 : ATTEMPTS[Math.min(n, ATTEMPTS.length) - 1].tier;

  return (
    <div ref={ref} className="grid gap-5 rounded-2xl border border-line-strong bg-card p-4 sm:p-6 md:grid-cols-[150px_1fr]">
      {/* tier ladder */}
      <div className="flex gap-2 md:flex-col-reverse md:justify-end">
        {TIERS.map((tier, i) => (
          <div
            key={tier}
            className={`relative flex-1 rounded-lg border px-3 py-3 font-mono text-[11px] transition-all duration-500 md:flex-none ${
              current === i && n > 0
                ? "border-signal bg-signal-soft text-ink"
                : "border-line text-muted"
            }`}
          >
            <p className="uppercase tracking-[0.14em]">{tier}</p>
            <p className="mt-0.5 text-[10px] opacity-70">{i === 0 ? "classify · extract" : i === 1 ? "default" : "plan · reason"}</p>
            {current === i && n > 0 && <span className="pulse-dot absolute right-2.5 top-2.5 h-1.5 w-1.5 rounded-full bg-signal text-signal" />}
          </div>
        ))}
      </div>

      {/* attempts */}
      <ol className="grid content-start gap-2 font-mono text-[12px]">
        {ATTEMPTS.map((a, i) => {
          const shown = i < n;
          return (
            <li
              key={a.model}
              className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2.5 transition-all duration-500 ${
                shown ? "translate-y-0 opacity-100" : "translate-y-1 opacity-25"
              } ${
                shown && a.kind === "ok"
                  ? "border-ok/50 bg-ok-soft"
                  : shown && a.kind === "fail"
                    ? "border-fail/30 bg-fail-soft/50"
                    : shown
                      ? "border-wait/40 bg-wait-soft/60"
                      : "border-line"
              }`}
            >
              <span className="w-5 text-muted">#{i + 1}</span>
              <span className="min-w-0 flex-1 truncate text-ink">{a.model}</span>
              <span className={`rounded px-1.5 py-0.5 text-[11px] ${shown ? (a.kind === "ok" ? "text-ok" : a.kind === "fail" ? "text-fail" : "text-wait") : "text-muted"}`}>
                {a.result}
              </span>
              <span className="w-full pl-8 text-[11px] text-muted sm:w-auto sm:pl-0 sm:text-right">→ {a.action}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
