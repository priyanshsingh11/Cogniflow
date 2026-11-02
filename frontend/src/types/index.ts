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
