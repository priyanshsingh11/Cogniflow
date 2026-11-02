/**
 * Typed fetch client for the Cogniflow backend.
 * Base URL comes from NEXT_PUBLIC_API_URL (inlined at build time).
 *
 * Automatically attaches `Authorization: Bearer <token>` when a token is
 * stored (see lib/auth.ts); a 401 lets callers redirect to /login.
 */

import { clearToken, getToken } from "@/lib/auth";
import type {
  AgentSummary,
  Approval,
  ChatMessage,
  ChatTurn,
  Conversation,
  KnowledgeDocument,
  McpToolSummary,
  Organization,
  RunStatus,
  StepInput,
  TokenResponse,
  User,
  Workflow,
  WorkflowRun,
  Workspace,
} from "@/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      // FormData sets its own multipart boundary header; only JSON bodies get a type.
      ...(typeof init.body === "string" ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });

  if (!res.ok) {
    if (res.status === 401 && token) {
      // Token expired or revoked — drop it so the UI stops claiming to be logged in.
      clearToken();
    }
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- Auth API ----

export function signup(payload: {
  email: string;
  password: string;
  display_name: string;
}): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/signup", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function login(payload: {
  email: string;
  password: string;
}): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchMe(): Promise<User> {
  return apiFetch<User>("/auth/me");
}

export function listOrganizations(): Promise<Organization[]> {
  return apiFetch<Organization[]>("/organizations");
}

export function listWorkspaces(
  orgId: string,
): Promise<Workspace[]> {
  return apiFetch<Workspace[]>(`/organizations/${orgId}/workspaces`);
}

export function getWorkspace(workspaceId: string): Promise<Workspace> {
  return apiFetch<Workspace>(`/workspaces/${workspaceId}`);
}

// ---- Documents (phase 3a) ----

export function listDocuments(workspaceId: string): Promise<KnowledgeDocument[]> {
  return apiFetch<KnowledgeDocument[]>(`/workspaces/${workspaceId}/documents`);
}

export function uploadDocument(
  workspaceId: string,
  file: File,
): Promise<KnowledgeDocument> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<KnowledgeDocument>(`/workspaces/${workspaceId}/documents`, {
    method: "POST",
    body: form,
  });
}

export function deleteDocument(
  workspaceId: string,
  documentId: string,
): Promise<void> {
  return apiFetch<void>(`/workspaces/${workspaceId}/documents/${documentId}`, {
    method: "DELETE",
  });
}

// ---- Chat (phase 3b) ----

export function listConversations(workspaceId: string): Promise<Conversation[]> {
  return apiFetch<Conversation[]>(`/workspaces/${workspaceId}/conversations`);
}

export function createConversation(
  workspaceId: string,
  title = "",
): Promise<Conversation> {
  return apiFetch<Conversation>(`/workspaces/${workspaceId}/conversations`, {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export function listMessages(
  workspaceId: string,
  conversationId: string,
): Promise<ChatMessage[]> {
  return apiFetch<ChatMessage[]>(
    `/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
  );
}

export function sendMessage(
  workspaceId: string,
  conversationId: string,
  content: string,
): Promise<ChatTurn> {
  return apiFetch<ChatTurn>(
    `/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
    { method: "POST", body: JSON.stringify({ content }) },
  );
}

// ---- Pickers for the workflow editor ----

export function listAgents(workspaceId: string): Promise<AgentSummary[]> {
  return apiFetch<AgentSummary[]>(`/workspaces/${workspaceId}/agents`);
}

export function listMcpTools(workspaceId: string): Promise<McpToolSummary[]> {
  return apiFetch<McpToolSummary[]>(`/workspaces/${workspaceId}/mcp/tools`);
}

// ---- Workflows and runs (phase 5) ----

export function listWorkflows(workspaceId: string): Promise<Workflow[]> {
  return apiFetch<Workflow[]>(`/workspaces/${workspaceId}/workflows`);
}

export function getWorkflow(workspaceId: string, workflowId: string): Promise<Workflow> {
  return apiFetch<Workflow>(`/workspaces/${workspaceId}/workflows/${workflowId}`);
}

export function createWorkflow(
  workspaceId: string,
  payload: { name: string; description?: string; steps: StepInput[] },
): Promise<Workflow> {
  return apiFetch<Workflow>(`/workspaces/${workspaceId}/workflows`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Saves the steps as a new immutable version; it becomes the current one. */
export function createWorkflowVersion(
  workspaceId: string,
  workflowId: string,
  steps: StepInput[],
): Promise<unknown> {
  return apiFetch<unknown>(`/workspaces/${workspaceId}/workflows/${workflowId}/versions`, {
    method: "POST",
    body: JSON.stringify({ steps }),
  });
}

export function triggerRun(
  workspaceId: string,
  workflowId: string,
  input: Record<string, unknown>,
): Promise<WorkflowRun> {
  return apiFetch<WorkflowRun>(`/workspaces/${workspaceId}/workflows/${workflowId}/runs`, {
    method: "POST",
    body: JSON.stringify({ input, idempotency_key: crypto.randomUUID() }),
  });
}

export function listRuns(
  workspaceId: string,
  options: { status?: RunStatus } = {},
): Promise<WorkflowRun[]> {
  const query = options.status ? `?status=${options.status}` : "";
  return apiFetch<WorkflowRun[]>(`/workspaces/${workspaceId}/runs${query}`);
}

export function getRun(workspaceId: string, runId: string): Promise<WorkflowRun> {
  return apiFetch<WorkflowRun>(`/workspaces/${workspaceId}/runs/${runId}`);
}

export function cancelRun(workspaceId: string, runId: string): Promise<WorkflowRun> {
  return apiFetch<WorkflowRun>(`/workspaces/${workspaceId}/runs/${runId}/cancel`, {
    method: "POST",
  });
}

// ---- Approvals (phase 6) ----

export function listApprovals(workspaceId: string): Promise<Approval[]> {
  return apiFetch<Approval[]>(`/workspaces/${workspaceId}/approvals`);
}

export function decideApproval(
  workspaceId: string,
  approvalId: string,
  action: "approve" | "reject",
  reason?: string,
): Promise<Approval> {
  return apiFetch<Approval>(`/workspaces/${workspaceId}/approvals/${approvalId}/decide`, {
    method: "POST",
    body: JSON.stringify({ action, reason: reason || null }),
  });
}
