"use client";

import { useEffect, useState } from "react";
import { getWorkspace } from "@/lib/api";
import type { Workspace } from "@/types";

/** Current member's workspace + role; `isAdmin` gates create/edit controls (the API enforces it too). */
export function useWorkspace(workspaceId: string) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  useEffect(() => {
    let cancelled = false;
    getWorkspace(workspaceId)
      .then((w) => !cancelled && setWorkspace(w))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);
  const role = workspace?.role ?? null;
  return {
    workspace,
    role,
    isAdmin: role === "owner" || role === "admin",
    canWrite: role === "owner" || role === "admin" || role === "member",
  };
}
