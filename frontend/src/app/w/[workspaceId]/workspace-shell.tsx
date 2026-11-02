"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, getWorkspace } from "@/lib/api";
import { clearToken, getToken } from "@/lib/auth";
import type { Workspace } from "@/types";

const NAV = [
  { href: "documents", label: "Documents" },
  { href: "chat", label: "Chat" },
  { href: "workflows", label: "Workflows" },
  { href: "runs", label: "Runs" },
  { href: "approvals", label: "Approvals" },
];

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
    <div className="flex flex-1 flex-col bg-zinc-50 dark:bg-black md:flex-row">
      <aside className="border-b border-zinc-200 bg-white px-4 py-4 dark:border-zinc-800 dark:bg-zinc-950 md:w-56 md:border-b-0 md:border-r">
        <Link
          href="/dashboard"
          className="text-xs font-medium uppercase tracking-widest text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          ← All workspaces
        </Link>
        <p className="mt-3 truncate text-base font-semibold text-black dark:text-zinc-50">
          {workspace?.name ?? "…"}
        </p>
        {workspace?.role && (
          <span className="mt-1 inline-block rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
            {workspace.role}
          </span>
        )}
        <nav className="mt-5 flex gap-2 md:flex-col">
          {NAV.map((item) => {
            const href = `/w/${workspaceId}/${item.href}`;
            const active = pathname.startsWith(href);
            return (
              <Link
                key={item.href}
                href={href}
                className={`rounded-md px-3 py-1.5 text-sm ${
                  active
                    ? "bg-black font-medium text-white dark:bg-zinc-50 dark:text-black"
                    : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <button
          onClick={signOut}
          className="mt-5 text-sm text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          Sign out
        </button>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col px-6 py-8">
        {error ? (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        ) : (
          children
        )}
      </main>
    </div>
  );
}
