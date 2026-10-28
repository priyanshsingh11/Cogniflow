"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ApiError,
  fetchMe,
  listOrganizations,
  listWorkspaces,
} from "@/lib/api";
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

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="flex flex-1 flex-col bg-zinc-50 px-6 py-12 dark:bg-black">
      <main className="mx-auto w-full max-w-2xl">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
              {user ? user.display_name : "…"}
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              {user?.email}
            </p>
          </div>
          <div className="flex gap-2">
            <Link
              href="/"
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
            >
              Home
            </Link>
            <button
              onClick={handleLogout}
              className="rounded-md bg-black px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
            >
              Sign out
            </button>
          </div>
        </div>

        <section className="mt-10">
          <h2 className="text-sm font-medium uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
            Your organizations &amp; workspaces
          </h2>
          {loading && (
            <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
              Loading…
            </p>
          )}
          {!loading && orgs.length === 0 && (
            <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
              No organizations found.
            </p>
          )}
          <div className="mt-4 grid gap-4">
            {orgs.map(({ org, workspaces }) => (
              <div
                key={org.id}
                className="rounded-md border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
              >
                <div className="flex items-center justify-between">
                  <p className="font-medium text-black dark:text-zinc-100">
                    {org.name}
                  </p>
                  {org.role && (
                    <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                      {org.role}
                    </span>
                  )}
                </div>
                <ul className="mt-3 grid gap-2 text-sm text-zinc-600 dark:text-zinc-400">
                  {workspaces.map((w) => (
                    <li
                      key={w.id}
                      className="flex items-center justify-between rounded border border-zinc-100 px-3 py-2 dark:border-zinc-800"
                    >
                      <span>{w.name}</span>
                      <code className="text-xs text-zinc-400">{w.id.slice(0, 8)}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
