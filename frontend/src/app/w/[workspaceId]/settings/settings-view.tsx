"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PageHeader } from "@/components/page-header";
import { ApiError, addMember, deleteWorkspace, listMembers, renameWorkspace } from "@/lib/api";
import { useWorkspace } from "@/lib/use-role";
import type { OrgMember } from "@/types";

const field =
  "w-full rounded-lg border border-line-strong bg-paper px-3.5 py-2 text-[13.5px] text-ink outline-none placeholder:text-muted focus:border-signal focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--signal)_20%,transparent)]";
const ROLES = ["viewer", "member", "admin"];

function msg(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : fallback;
}

export function SettingsView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const router = useRouter();
  const { workspace, isAdmin, canWrite } = useWorkspace(workspaceId);
  const orgId = workspace?.org_id;
  const [name, setName] = useState<string | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadMembers = useCallback(() => {
    if (!orgId) return;
    listMembers(orgId).then(setMembers).catch((e) => setError(msg(e, "Could not load members")));
  }, [orgId]);
  useEffect(loadMembers, [loadMembers]);

  async function rename(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await renameWorkspace(workspaceId, (name ?? workspace?.name ?? "").trim());
      setNotice("Workspace renamed. Reload to see it in the sidebar.");
    } catch (err) {
      setError(msg(err, "Could not rename"));
    }
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId) return;
    setError(null);
    setNotice(null);
    try {
      await addMember(orgId, email, role);
      setEmail("");
      setNotice("Member added.");
      loadMembers();
    } catch (err) {
      setError(msg(err, "Could not add member (they must already have an account)"));
    }
  }

  async function remove() {
    if (!confirm(`Delete workspace "${workspace?.name}" and everything in it? This cannot be undone.`)) return;
    try {
      await deleteWorkspace(workspaceId);
      router.replace("/dashboard");
    } catch (err) {
      setError(msg(err, "Could not delete the workspace"));
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader eyebrow="Admin" title={<>Workspace <em>settings</em></>}>
        Rename the workspace and manage who in the organization can use it.
      </PageHeader>
      {error && <ErrorNote>{error}</ErrorNote>}
      {notice && <p className="mt-5 rounded-lg border border-ok/30 bg-ok-soft px-3.5 py-2.5 text-[13px] text-ok">{notice}</p>}

      <section className="mt-6 rounded-2xl border border-line-strong bg-card p-5">
        <p className="eyebrow">Name</p>
        <form onSubmit={(e) => void rename(e)} className="mt-3 flex gap-2">
          <input className={field} disabled={!canWrite} value={name ?? workspace?.name ?? ""} onChange={(e) => setName(e.target.value)} />
          <button disabled={!canWrite} className="btn-primary">Rename</button>
        </form>
      </section>

      <section className="mt-4 rounded-2xl border border-line-strong bg-card p-5">
        <p className="eyebrow">Organization members</p>
        <ul className="mt-3 divide-y divide-line">
          {members.map((m) => (
            <li key={m.user_id} className="flex items-center justify-between py-2.5 text-[13.5px]">
              <span><span className="font-medium">{m.display_name}</span> <span className="font-mono text-[11.5px] text-muted">{m.email}</span></span>
              <span className="rounded-full border border-line-strong px-2.5 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted">{m.role}</span>
            </li>
          ))}
        </ul>
        {isAdmin && (
          <form onSubmit={(e) => void invite(e)} className="mt-4 grid gap-2 sm:grid-cols-[1fr_8rem_auto]">
            <input required type="email" className={field} placeholder="Email of an existing user" value={email} onChange={(e) => setEmail(e.target.value)} />
            <select className={field} value={role} onChange={(e) => setRole(e.target.value)}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select>
            <button className="btn-primary">Add</button>
          </form>
        )}
      </section>

      {isAdmin && (
        <section className="mt-4 rounded-2xl border border-fail/40 bg-card p-5">
          <p className="eyebrow !text-fail">Danger zone</p>
          <p className="mt-2 text-[13.5px] text-muted">Deleting a workspace removes its documents, workflows, runs and agents.</p>
          <button onClick={() => void remove()} className="btn-ghost mt-3 !border-fail/50 !text-fail">Delete workspace</button>
        </section>
      )}
    </div>
  );
}
