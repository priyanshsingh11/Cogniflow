/**
 * Token + user persistence (localStorage).
 * Phase 1 decision: JWT stored in localStorage and attached as a Bearer
 * header by lib/api.ts. Revisit with httpOnly cookies if this ever ships
 * to untrusted environments.
 */

import type { User } from "@/types";

const TOKEN_KEY = "cogniflow_token";
const USER_KEY = "cogniflow_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

/** Cache the user object so pages can render instantly; /auth/me revalidates. */
export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function setStoredUser(user: User): void {
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}
