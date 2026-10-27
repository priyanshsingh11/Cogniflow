/**
 * Placeholder shared types.
 * These will be refined against the actual backend schema in Phase 1
 * (see db-schema.mmd once created).
 */

export interface User {
  id: string;
  email: string;
  name: string;
}

export interface Workspace {
  id: string;
  organizationId: string;
  name: string;
}

export type RunStatus =
  | "pending"
  | "running"
  | "awaiting_approval"
  | "succeeded"
  | "failed";

export interface Workflow {
  id: string;
  workspaceId: string;
  name: string;
  status: "draft" | "active";
}

export interface WorkflowRun {
  id: string;
  workflowId: string;
  status: RunStatus;
  startedAt: string | null;
  finishedAt: string | null;
}
