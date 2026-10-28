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

  return (
    <section className="mt-6 rounded-md border border-zinc-200 bg-white px-4 py-3 text-sm dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="font-medium text-zinc-900 dark:text-zinc-50">Backend status</h2>
      {result.state === "loading" && <p className="mt-2 text-zinc-500">Checking…</p>}
      {result.state === "error" && (
        <p className="mt-2 text-red-600 dark:text-red-400">Unreachable: {result.message}</p>
      )}
      {result.state === "done" && (
        <ul className="mt-2 space-y-1">
          {Object.entries(result.deps).map(([name, status]) => (
            <li key={name} className="flex justify-between text-zinc-700 dark:text-zinc-300">
              <span>{name}</span>
              <span className={status === "ok" ? "text-green-600" : "text-red-600"}>{status}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
