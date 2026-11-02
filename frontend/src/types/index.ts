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

// ---- Knowledge (phase 3) ----

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface KnowledgeDocument {
  id: string;
  filename: string;
  status: DocumentStatus;
  size_bytes: number;
  error_message: string | null;
  created_at: string;
}

export interface Passage {
  document_id: string;
  filename: string;
  chunk_index: number;
  content: string;
  score: number;
}

// ---- Chat (phase 3b) ----

export interface Conversation {
  id: string;
  title: string;
  user_id: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string | null;
  citations: Passage[];
  meta: { tier?: string; route_reason?: string } | null;
  created_at: string;
}

export interface ChatTurn {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  tier: string;
  route_reason: string;
}

// ---- Agents and MCP tools (pickers in the workflow editor) ----

export interface AgentSummary {
  id: string;
  name: string;
  role: string;
}

export interface McpToolSummary {
  id: string;
  server_name: string;
  name: string;
  description: string | null;
  approved: boolean;
  requires_approval: boolean;
  active: boolean;
}

// ---- Workflows (phase 5) ----

export type StepType =
  | "llm"
  | "knowledge_search"
  | "mcp_tool"
  | "condition"
  | "agent"
  | "coordinator"
  | "approval";

export interface WorkflowStep {
  id: string;
  name: string;
  position: number;
  type: StepType;
  config: Record<string, unknown>;
}

export interface WorkflowVersion {
  id: string;
  workflow_id: string;
  version: number;
  steps: WorkflowStep[];
  created_at: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  current_version_id: string | null;
  current_version: WorkflowVersion | null;
  created_at: string;
}

export interface StepInput {
  name: string;
  type: StepType;
  position: number;
  config: Record<string, unknown>;
}

export type RunStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface StepRun {
  id: string;
  step_name: string;
  attempt: number;
  status: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  llm_calls_count: number;
  tool_calls_count: number;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  workflow_version_id: string;
  status: RunStatus;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  step_runs: StepRun[];
}

// ---- Approvals (phase 6) ----

export interface Approval {
  id: string;
  workflow_run_id: string | null;
  step_run_id: string | null;
  status: "pending" | "approved" | "rejected";
  reason: string | null;
  description: string | null;
  details: Record<string, unknown> | null;
  requested_at: string;
  decided_at: string | null;
}
