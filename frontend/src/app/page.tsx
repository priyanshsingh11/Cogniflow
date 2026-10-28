import Link from "next/link";
import DepsStatus from "./deps-status";

const FEATURES = [
  "Document RAG with source citations",
  "Multi-step workflow execution",
  "MCP tool integrations",
  "Human approval steps",
  "Execution history, token usage & cost",
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-zinc-50 px-6 py-24 dark:bg-black">
      <main className="w-full max-w-2xl">
        <p className="text-sm font-medium uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
          Cogniflow
        </p>
        <div className="flex items-center justify-between">
          <h1 className="mt-2 text-4xl font-semibold tracking-tight text-black dark:text-zinc-50">
            AI Workbench
          </h1>
          <nav className="flex gap-2">
            <Link
              href="/login"
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className="rounded-md bg-black px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
            >
              Sign up
            </Link>
          </nav>
        </div>
        <p className="mt-4 text-lg leading-8 text-zinc-600 dark:text-zinc-400">
          Build, run, and monitor multi-step AI workflows — combining agents,
          company documents, and external tools in a single workspace.
        </p>
        <ul className="mt-8 grid gap-3 text-sm text-zinc-700 dark:text-zinc-300 sm:grid-cols-2">
          {FEATURES.map((feature) => (
            <li
              key={feature}
              className="rounded-md border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900"
            >
              {feature}
            </li>
          ))}
        </ul>
        <DepsStatus />
        <p className="mt-10 rounded-md border border-dashed border-zinc-300 px-4 py-3 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
          Auth is live (Phase 1): sign up to get a personal workspace. Upload +
          chat and the workflow editor arrive in later phases.
        </p>
      </main>
    </div>
  );
}
