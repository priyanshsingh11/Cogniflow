/**
 * Typed fetch client for the Cogniflow backend.
 * Base URL comes from NEXT_PUBLIC_API_URL (inlined at build time).
 *
 * Automatically attaches `Authorization: Bearer <token>` when a token is
 * stored (see lib/auth.ts); a 401 lets callers redirect to /login.
 */

import { clearToken, getToken } from "@/lib/auth";
import type {
  Agent,
  AgentInput,
  AgentRunResult,
  AgentSummary,
  AskResult,
  CoordinatorResult,
  McpServer,
  McpTool,
  McpToolCall,
  OrgMember,
  Passage,
  WorkflowTrigger,
  Approval,
  AuditLog,
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
  UsageReport,
} from "@/types";

export const API_BASE_URL =
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

// ---- Usage and audit (phase 8) ----

export function getUsage(workspaceId: string, days: number): Promise<UsageReport> {
  return apiFetch<UsageReport>(`/workspaces/${workspaceId}/usage?days=${days}`);
}

export function listAuditLogs(
  workspaceId: string,
  opts: { action?: string; limit?: number; offset?: number } = {},
): Promise<AuditLog[]> {
  const params = new URLSearchParams();
  if (opts.action) params.set("action", opts.action);
  params.set("limit", String(opts.limit ?? 50));
  params.set("offset", String(opts.offset ?? 0));
  return apiFetch<AuditLog[]>(`/workspaces/${workspaceId}/audit-logs?${params}`);
}

// ---- Agents and coordinator ----

const ws = (id: string) => `/workspaces/${id}`;
const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export function listAgentsFull(workspaceId: string): Promise<Agent[]> {
  return apiFetch<Agent[]>(`${ws(workspaceId)}/agents`);
}
export function createAgent(workspaceId: string, payload: AgentInput): Promise<Agent> {
  return apiFetch<Agent>(`${ws(workspaceId)}/agents`, json("POST", payload));
}
export function updateAgent(workspaceId: string, id: string, payload: Partial<AgentInput>): Promise<Agent> {
  return apiFetch<Agent>(`${ws(workspaceId)}/agents/${id}`, json("PATCH", payload));
}
export function deleteAgent(workspaceId: string, id: string): Promise<void> {
  return apiFetch<void>(`${ws(workspaceId)}/agents/${id}`, { method: "DELETE" });
}
export function runAgent(workspaceId: string, id: string, input: string): Promise<AgentRunResult> {
  return apiFetch<AgentRunResult>(`${ws(workspaceId)}/agents/${id}/run`, json("POST", { input }));
}
export function runCoordinator(workspaceId: string, goal: string): Promise<CoordinatorResult> {
  return apiFetch<CoordinatorResult>(`${ws(workspaceId)}/coordinator/run`, json("POST", { goal }));
}

// ---- MCP servers, tools, tool calls ----

export function listMcpServers(workspaceId: string): Promise<McpServer[]> {
  return apiFetch<McpServer[]>(`${ws(workspaceId)}/mcp/servers`);
}
export function createMcpServer(
  workspaceId: string,
  payload: {
    name: string;
    transport: "stdio" | "http";
    command?: string;
    args?: string[];
    url?: string;
    credentials?: Record<string, unknown>;
  },
): Promise<McpServer> {
  return apiFetch<McpServer>(`${ws(workspaceId)}/mcp/servers`, json("POST", payload));
}
export function deleteMcpServer(workspaceId: string, id: string): Promise<void> {
  return apiFetch<void>(`${ws(workspaceId)}/mcp/servers/${id}`, { method: "DELETE" });
}
export function discoverMcpServer(
  workspaceId: string,
  id: string,
): Promise<{ server_id: string; status: string; tools: McpTool[] }> {
  return apiFetch(`${ws(workspaceId)}/mcp/servers/${id}/discover`, { method: "POST" });
}
export function listMcpToolsFull(workspaceId: string, serverId?: string): Promise<McpTool[]> {
  const q = serverId ? `?server_id=${serverId}` : "";
  return apiFetch<McpTool[]>(`${ws(workspaceId)}/mcp/tools${q}`);
}
export function patchMcpTool(
  workspaceId: string,
  id: string,
  payload: { approved?: boolean; requires_approval?: boolean },
): Promise<McpTool> {
  return apiFetch<McpTool>(`${ws(workspaceId)}/mcp/tools/${id}`, json("PATCH", payload));
}
export function listToolCalls(workspaceId: string, limit = 50): Promise<McpToolCall[]> {
  return apiFetch<McpToolCall[]>(`${ws(workspaceId)}/mcp/tool-calls?limit=${limit}`);
}

// ---- Knowledge search / ask ----

export function searchKnowledge(workspaceId: string, query: string, topK = 6): Promise<{ query: string; passages: Passage[] }> {
  return apiFetch(`${ws(workspaceId)}/knowledge/search`, json("POST", { query, top_k: topK }));
}
export function askKnowledge(workspaceId: string, question: string): Promise<AskResult> {
  return apiFetch<AskResult>(`${ws(workspaceId)}/knowledge/ask`, json("POST", { question }));
}

// ---- Organizations, members, workspaces ----

export function createOrganization(name: string): Promise<Organization> {
  return apiFetch<Organization>("/organizations", json("POST", { name }));
}
export function listMembers(orgId: string): Promise<OrgMember[]> {
  return apiFetch<OrgMember[]>(`/organizations/${orgId}/members`);
}
export function addMember(orgId: string, email: string, role: string): Promise<OrgMember> {
  return apiFetch<OrgMember>(`/organizations/${orgId}/members`, json("POST", { email, role }));
}
export function createWorkspace(orgId: string, name: string): Promise<Workspace> {
  return apiFetch<Workspace>(`/organizations/${orgId}/workspaces`, json("POST", { name }));
}
export function renameWorkspace(workspaceId: string, name: string): Promise<Workspace> {
  return apiFetch<Workspace>(`/workspaces/${workspaceId}/rename`, json("POST", { name }));
}
export function deleteWorkspace(workspaceId: string): Promise<void> {
  return apiFetch<void>(`/workspaces/${workspaceId}`, { method: "DELETE" });
}
export function deleteWorkflow(workspaceId: string, workflowId: string): Promise<void> {
  return apiFetch<void>(`${ws(workspaceId)}/workflows/${workflowId}`, { method: "DELETE" });
}

// ---- Triggers (phase 10) ----

const trig = (ws_: string, wf: string) => `/workspaces/${ws_}/workflows/${wf}/triggers`;

export function listTriggers(workspaceId: string, workflowId: string): Promise<WorkflowTrigger[]> {
  return apiFetch<WorkflowTrigger[]>(trig(workspaceId, workflowId));
}
export function createTrigger(
  workspaceId: string,
  workflowId: string,
  payload: { type: "schedule" | "webhook"; cron?: string; timezone?: string; input?: Record<string, unknown> },
): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>(trig(workspaceId, workflowId), json("POST", payload));
}
export function updateTrigger(
  workspaceId: string,
  workflowId: string,
  id: string,
  payload: { enabled?: boolean; cron?: string; timezone?: string; input?: Record<string, unknown> },
): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>(`${trig(workspaceId, workflowId)}/${id}`, json("PATCH", payload));
}
export function rotateTrigger(workspaceId: string, workflowId: string, id: string): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>(`${trig(workspaceId, workflowId)}/${id}/rotate`, { method: "POST" });
}
export function deleteTrigger(workspaceId: string, workflowId: string, id: string): Promise<void> {
  return apiFetch<void>(`${trig(workspaceId, workflowId)}/${id}`, { method: "DELETE" });
}
