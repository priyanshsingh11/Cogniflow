"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { ApiError, getWorkspace } from "@/lib/api";
import { clearToken, getToken } from "@/lib/auth";
import type { Workspace } from "@/types";

const NAV: { href: string; label: string; adminOnly?: boolean }[] = [
  { href: "documents", label: "Documents" },
  { href: "chat", label: "Chat" },
  { href: "knowledge", label: "Knowledge" },
  { href: "agents", label: "Agents" },
  { href: "mcp", label: "MCP tools" },
  { href: "workflows", label: "Workflows" },
  { href: "runs", label: "Runs" },
  { href: "approvals", label: "Approvals" },
  { href: "usage", label: "Usage" },
  { href: "audit", label: "Audit log", adminOnly: true },
  { href: "settings", label: "Settings" },
];

const ADMIN_ROLES = ["owner", "admin"];

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    getWorkspace(workspaceId)
      .then(setWorkspace)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
        } else {
          setError(err instanceof ApiError ? err.message : "Could not load workspace");
        }
      });
  }, [workspaceId, router]);

  function signOut() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="flex flex-1 flex-col md:flex-row">
      <aside className="flex flex-col border-b border-line bg-paper-2/50 px-4 py-5 md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:border-b-0 md:border-r">
        <Link href="/dashboard" aria-label="All workspaces" className="w-fit px-1"><Logo size={24} /></Link>
        <div className="mt-6 rounded-xl border border-line-strong bg-card px-3.5 py-3">
          <p className="eyebrow !text-[10px]">Workspace</p>
          <p className="mt-1 truncate text-[15px] font-semibold tracking-tight text-ink">{workspace?.name ?? "…"}</p>
          {workspace?.role && (
            <span className="mt-1.5 inline-block rounded-full bg-signal-soft px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-signal">
              {workspace.role}
            </span>
          )}
        </div>
        <nav aria-label="Workspace" className="mt-5 flex gap-1 overflow-x-auto md:flex-col md:overflow-visible">
          {NAV.filter(
            (item) => !item.adminOnly || (workspace?.role && ADMIN_ROLES.includes(workspace.role)),
          ).map((item) => {
            const href = `/w/${workspaceId}/${item.href}`;
            const active = pathname.startsWith(href);
            return (
              <Link
                key={item.href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`relative whitespace-nowrap rounded-lg px-3 py-2 text-[13.5px] transition-colors ${
                  active ? "bg-ink font-medium text-paper" : "text-ink-2 hover:bg-paper-2"
                }`}
              >
                {active && <span className="absolute left-0 top-1/2 hidden h-4 w-[3px] -translate-y-1/2 rounded-r bg-signal md:block" />}
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto flex items-center justify-between pt-6 text-[12.5px] text-muted">
          <Link href="/dashboard" className="hover:text-ink">← Workspaces</Link>
          <button onClick={signOut} className="hover:text-ink">Sign out</button>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col px-5 py-8 sm:px-8">
        {error ? <p className="text-sm text-fail">{error}</p> : children}
      </main>
    </div>
  );
}
