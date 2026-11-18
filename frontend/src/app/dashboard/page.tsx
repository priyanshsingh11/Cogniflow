"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ApiError,
  createOrganization,
  createWorkspace,
  fetchMe,
  listOrganizations,
  listWorkspaces,
} from "@/lib/api";
import { Logo } from "@/components/logo";
import { EmptyState, Icon, SkeletonRows, Stat } from "@/components/page-header";
import { clearToken, getStoredUser, getToken } from "@/lib/auth";
import type { Organization, User, Workspace } from "@/types";

type OrgWithWorkspaces = { org: Organization; workspaces: Workspace[] };

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [orgs, setOrgs] = useState<OrgWithWorkspaces[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    // Show cached user instantly, then revalidate against the API.
    async function load() {
      setUser(getStoredUser());
      try {
        const me = await fetchMe();
        setUser(me);
        const myOrgs = await listOrganizations();
        const withWorkspaces = await Promise.all(
          myOrgs.map(async (org) => ({
            org,
            workspaces: await listWorkspaces(org.id),
          })),
        );
        setOrgs(withWorkspaces);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
        }
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [router]);

  async function reload() {
    const myOrgs = await listOrganizations();
    setOrgs(await Promise.all(myOrgs.map(async (org) => ({ org, workspaces: await listWorkspaces(org.id) }))));
  }

  async function addOrg() {
    const name = prompt("Organization name");
    if (!name?.trim()) return;
    try {
      await createOrganization(name.trim());
      await reload();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Could not create organization");
    }
  }

  async function addWorkspace(orgId: string) {
    const name = prompt("Workspace name");
    if (!name?.trim()) return;
    try {
      await createWorkspace(orgId, name.trim());
      await reload();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Could not create workspace");
    }
  }

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  const workspaceCount = orgs.reduce((n, o) => n + o.workspaces.length, 0);
  const firstName = user?.display_name?.split(" ")[0];

  return (
    <div className="flex flex-1 flex-col">
      <header className="sticky top-0 z-40 border-b border-line/70 bg-paper/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
          <Link href="/" aria-label="Cogniflow home"><Logo /></Link>
          <div className="flex items-center gap-4">
            <span className="hidden font-mono text-[11px] text-muted sm:block">{user?.email}</span>
            <button onClick={handleLogout} className="btn-ghost !px-3.5 !py-1.5 text-[13px]">Sign out</button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl px-6 pb-20">
        {/* greeting */}
        <section className="relative">
          <div className="dot-grid fade-edges absolute inset-x-0 -top-px h-64 opacity-60" aria-hidden="true" />
          <div className="rise relative pb-10 pt-14">
            <p className="eyebrow">Dashboard</p>
            <h1 className="display mt-2 text-5xl leading-[1.02] sm:text-6xl">
              {firstName ? <>Welcome back, <em className="text-signal">{firstName}</em>.</> : "…"}
            </h1>
            <p className="mt-3 max-w-md text-[14.5px] leading-6 text-muted">
              Pick a workspace to chat with your documents, run workflows and review what happened.
            </p>
          </div>
        </section>

        {!loading && orgs.length > 0 && (
          <div className="rise grid grid-cols-2 gap-3 sm:max-w-md" style={{ "--d": "80ms" } as React.CSSProperties}>
            <Stat label="Organizations" value={orgs.length} />
            <Stat label="Workspaces" value={workspaceCount} tone="signal" />
          </div>
        )}

        {loading && <SkeletonRows n={2} />}
        {!loading && orgs.length === 0 && (
          <EmptyState icon={<Icon name="flow" />} title={<>No <em>workspaces</em> yet</>}>
            Your organization and workspace should appear here after signup. Try refreshing.
          </EmptyState>
        )}

        {!loading && (
          <div className="mt-6"><button onClick={() => void addOrg()} className="btn-ghost text-[13px]">+ New organization</button></div>
        )}

        <div className="mt-10 grid gap-10">
          {orgs.map(({ org, workspaces }, oi) => (
            <section key={org.id} className="rise" style={{ "--d": `${120 + oi * 80}ms` } as React.CSSProperties}>
              <div className="flex items-center justify-between gap-3 border-b border-line pb-3">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-ink font-semibold text-paper">
                    {org.name.charAt(0).toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-[17px] font-semibold tracking-tight text-ink">{org.name}</p>
                    <p className="font-mono text-[11px] text-muted">{workspaces.length} workspace{workspaces.length === 1 ? "" : "s"}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {(org.role === "owner" || org.role === "admin") && (
                    <button onClick={() => void addWorkspace(org.id)} className="btn-ghost !px-3 !py-1 text-[12px]">+ Workspace</button>
                  )}
                  {org.role && (
                    <span className="rounded-full border border-line-strong px-2.5 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted">
                      {org.role}
                    </span>
                  )}
                </div>
              </div>

              <ul className="mt-5 grid gap-4 sm:grid-cols-2">
                {workspaces.map((w) => (
                  <li key={w.id} className="group relative rounded-2xl border border-line-strong bg-card p-5 transition-all hover:-translate-y-0.5 hover:border-signal hover:shadow-[0_14px_30px_-18px_var(--signal)]">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="eyebrow !text-[10px]">Workspace</p>
                        <p className="display mt-1 truncate text-3xl leading-tight">{w.name}</p>
                      </div>
                      <Link
                        href={`/w/${w.id}/documents`}
                        aria-label={`Open ${w.name}`}
                        className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line-strong text-ink transition-colors group-hover:border-signal group-hover:bg-signal group-hover:text-signal-ink after:absolute after:inset-0 after:rounded-2xl"
                      >
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2 7h10M8 3l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      </Link>
                    </div>
                    <div className="relative z-10 mt-5 flex flex-wrap gap-1.5">
                      {[["documents", "Documents"], ["chat", "Chat"], ["workflows", "Workflows"], ["runs", "Runs"]].map(([h, l]) => (
                        <Link
                          key={h}
                          href={`/w/${w.id}/${h}`}
                          className="rounded-full border border-line bg-paper px-3 py-1 font-mono text-[11px] text-ink-2 transition-colors hover:border-ink hover:text-ink"
                        >
                          {l}
                        </Link>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
