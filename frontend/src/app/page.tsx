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
        <h1 className="mt-2 text-4xl font-semibold tracking-tight text-black dark:text-zinc-50">
          AI Workbench
        </h1>
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
          Frontend scaffold ready (Phase 0). Sign-in, upload + chat, and the
          workflow editor arrive in Phase 7.
        </p>
      </main>
    </div>
  );
}
