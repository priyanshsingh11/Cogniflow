/**
 * Minimal typed fetch client for the AI Workbench backend.
 * Base URL comes from NEXT_PUBLIC_API_URL (inlined at build time).
 *
 * Phase 1 will add JWT handling (attach `Authorization: Bearer <token>`)
 * once the auth endpoints exist.
 */

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
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (!res.ok) {
    throw new ApiError(
      res.status,
      `API request failed: ${res.status} ${res.statusText}`,
    );
  }

  return (await res.json()) as T;
}
