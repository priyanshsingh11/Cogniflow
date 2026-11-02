"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, createWorkflowVersion, getWorkflow, triggerRun } from "@/lib/api";
import type { Workflow } from "@/types";
import { WorkflowEditor } from "../workflow-editor";

export function WorkflowDetailView() {
  const { workspaceId, workflowId } = useParams<{ workspaceId: string; workflowId: string }>();
  const router = useRouter();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runInput, setRunInput] = useState("{}");
  const [starting, setStarting] = useState(false);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getWorkflow(workspaceId, workflowId)
      .then((wf) => !cancelled && setWorkflow(wf))
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : "Could not load the workflow");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, workflowId, reloads]);

  async function run() {
    setError(null);
    let input: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(runInput || "{}");
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error();
      input = parsed as Record<string, unknown>;
    } catch {
      return setError('Run input must be a JSON object, e.g. {"topic": "indexes"}.');
    }
    setStarting(true);
    try {
      const created = await triggerRun(workspaceId, workflowId, input);
      router.push(`/w/${workspaceId}/runs/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the run");
      setStarting(false);
    }
  }

  if (loadError) return <p className="text-sm text-red-600 dark:text-red-400">{loadError}</p>;
  if (!workflow) return <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>;

  const version = workflow.current_version;
  return (
    <div className="mx-auto w-full max-w-3xl">
      <Link href={`/w/${workspaceId}/workflows`} className="text-sm text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-100">
        ← Workflows
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">{workflow.name}</h1>
      {workflow.description && <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{workflow.description}</p>}

      <section className="mt-6 rounded-md border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-sm font-semibold text-black dark:text-zinc-100">Run this workflow</h2>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          Runs version {version?.version}. Input is available to steps as <code>{"{{ input.field }}"}</code>.
        </p>
        <textarea
          value={runInput}
          onChange={(e) => setRunInput(e.target.value)}
          rows={3}
          spellCheck={false}
          className="mt-3 w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 font-mono text-sm text-black outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
        />
        <div className="mt-3 flex items-center gap-3">
          <button onClick={() => void run()} disabled={starting} className="rounded-md bg-black px-4 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200">
            {starting ? "Starting…" : "Run"}
          </button>
          {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
      </section>

      <h2 className="mt-8 text-sm font-semibold uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
        Steps (version {version?.version})
      </h2>
      <div className="mt-3">
        <WorkflowEditor
          key={workflow.current_version_id ?? "none"}
          isNew={false}
          workspaceId={workspaceId}
          saving={saving}
          initialSteps={version?.steps ?? []}
          onSave={async (value) => {
            setSaving(true);
            setError(null);
            setMessage(null);
            try {
              await createWorkflowVersion(workspaceId, workflowId, value.steps);
              setMessage("Saved as a new version. Earlier runs keep the version they ran.");
              setReloads((n) => n + 1);
            } catch (err) {
              setError(err instanceof ApiError ? err.message : "Could not save");
            } finally {
              setSaving(false);
            }
          }}
        />
        {message && <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-400">{message}</p>}
      </div>
    </div>
  );
}
