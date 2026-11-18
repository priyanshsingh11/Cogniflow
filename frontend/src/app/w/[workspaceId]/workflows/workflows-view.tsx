"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { EmptyState, ErrorNote, Icon, PageHeader, SkeletonRows } from "@/components/page-header";
import { ApiError, listWorkflows } from "@/lib/api";
import type { StepType, Workflow } from "@/types";

const STEP_LABEL: Record<StepType, string> = {
  llm: "llm",
  knowledge_search: "search",
  mcp_tool: "tool",
  condition: "if",
  agent: "agent",
  coordinator: "coord",
  approval: "approval",
};

export function WorkflowsView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listWorkflows(workspaceId)
      .then((list) => !cancelled && setWorkflows(list))
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load workflows");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const newBtn = (
    <Link href={`/w/${workspaceId}/workflows/new`} className="btn-primary">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
      New workflow
    </Link>
  );

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader eyebrow="Automation" title={<>Your <em>workflows</em></>} action={newBtn}>
        A workflow is a saved, versioned list of steps. Run it any time and inspect every step afterwards.
      </PageHeader>
      {error && <ErrorNote>{error}</ErrorNote>}
      {workflows === null && !error && <SkeletonRows />}
      {workflows?.length === 0 && (
        <EmptyState icon={<Icon name="flow" />} title={<>Chain your first <em>workflow</em></>} action={newBtn}>
          Combine model calls, document search, tools and human approvals into one repeatable run.
        </EmptyState>
      )}
      <ul className="mt-6 grid gap-3 sm:grid-cols-2">
        {workflows?.map((w, i) => {
          const steps = w.current_version?.steps ?? [];
          return (
            <li key={w.id} className="step-in" style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}>
              <Link
                href={`/w/${workspaceId}/workflows/${w.id}`}
                className="group flex h-full flex-col rounded-2xl border border-line-strong bg-card p-5 transition-all hover:-translate-y-0.5 hover:border-signal hover:shadow-[0_14px_30px_-18px_var(--signal)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="truncate text-[16px] font-semibold tracking-tight text-ink">{w.name}</p>
                  <span className="shrink-0 rounded-full border border-line-strong px-2 py-0.5 font-mono text-[10.5px] text-muted">
                    v{w.current_version?.version ?? "–"}
                  </span>
                </div>
                <p className="mt-1.5 line-clamp-2 min-h-10 text-[13px] leading-5 text-muted">
                  {w.description || "No description."}
                </p>
                {/* mini pipeline */}
                <div className="mt-4 flex flex-wrap items-center gap-1.5 font-mono text-[10.5px] text-ink-2">
                  {steps.length === 0 && <span className="text-muted">no steps</span>}
                  {steps.slice(0, 5).map((st, j) => (
                    <span key={st.id} className="flex items-center gap-1.5">
                      <span className="rounded-md border border-line bg-paper px-1.5 py-0.5">{STEP_LABEL[st.type]}</span>
                      {j < Math.min(steps.length, 5) - 1 && <span className="text-signal">→</span>}
                    </span>
                  ))}
                  {steps.length > 5 && <span className="text-muted">+{steps.length - 5}</span>}
                </div>
                <p className="mt-4 flex items-center justify-between border-t border-line pt-3 font-mono text-[11px] text-muted">
                  <span>{steps.length} steps</span>
                  <span className="transition-colors group-hover:text-signal">open →</span>
                </p>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
