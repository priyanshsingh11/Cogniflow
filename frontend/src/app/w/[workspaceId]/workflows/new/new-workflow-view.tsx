"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, createWorkflow } from "@/lib/api";
import { WorkflowEditor } from "../workflow-editor";

export function NewWorkflowView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="mx-auto w-full max-w-3xl">
      <Link href={`/w/${workspaceId}/workflows`} className="text-sm text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-100">
        ← Workflows
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">New workflow</h1>
      <div className="mt-6">
        <WorkflowEditor
          isNew
          workspaceId={workspaceId}
          saving={saving}
          initialSteps={[]}
          onSave={async (value) => {
            setSaving(true);
            setError(null);
            try {
              const wf = await createWorkflow(workspaceId, {
                name: value.name,
                description: value.description || undefined,
                steps: value.steps,
              });
              router.push(`/w/${workspaceId}/workflows/${wf.id}`);
            } catch (err) {
              setError(err instanceof ApiError ? err.message : "Could not create the workflow");
              setSaving(false);
            }
          }}
        />
        {error && <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>
    </div>
  );
}
