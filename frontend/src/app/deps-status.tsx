"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

type DepsResult =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "done"; deps: Record<string, string> };

export default function DepsStatus() {
  const [result, setResult] = useState<DepsResult>({ state: "loading" });

  useEffect(() => {
    apiFetch<Record<string, string>>("/health/deps")
      .then((deps) => setResult({ state: "done", deps }))
      .catch((err: Error) => setResult({ state: "error", message: err.message }));
  }, []);

  const dot = (ok: boolean) => (
    <span className={`inline-block h-1.5 w-1.5 rounded-full ${ok ? "bg-ok" : "bg-fail"}`} />
  );

  return (
    <section aria-label="Backend status" className="rounded-xl border border-line-strong bg-card px-4 py-3 font-mono text-[12px]">
      <p className="mb-2 text-[10px] uppercase tracking-[0.14em] text-muted">Live backend status</p>
      {result.state === "loading" && <p className="text-muted">Checking…</p>}
      {result.state === "error" && (
        <p className="flex items-center gap-2 text-fail">{dot(false)} Unreachable</p>
      )}
      {result.state === "done" && (
        <ul className="flex flex-wrap gap-x-5 gap-y-1.5">
          {Object.entries(result.deps).map(([name, status]) => (
            <li key={name} className="flex items-center gap-2 text-ink-2">
              {dot(status === "ok")}
              {name}
              <span className={status === "ok" ? "text-ok" : "text-fail"}>{status}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
