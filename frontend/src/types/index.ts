/** Shared types mirroring the backend Pydantic schemas (Phase 1 auth/tenancy). */

export interface User {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export type Role = "owner" | "admin" | "member" | "viewer";

export interface Organization {
  id: string;
  name: string;
  slug: string;
  role: Role | null;
  created_at: string;
}

export interface Workspace {
  id: string;
  org_id: string;
  name: string;
  role: Role | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
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
