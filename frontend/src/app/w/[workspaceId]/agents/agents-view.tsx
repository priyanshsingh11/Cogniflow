"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorNote, PageHeader, SkeletonRows } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import {
  ApiError,
  createAgent,
  deleteAgent,
  listAgentsFull,
  runAgent,
  runCoordinator,
  updateAgent,
} from "@/lib/api";
import { useWorkspace } from "@/lib/use-role";
import { AGENT_ROLES, TIERS } from "@/types";
import type { Agent, AgentInput, AgentRunResult, CoordinatorResult } from "@/types";

const field =
  "w-full rounded-lg border border-line-strong bg-paper px-3.5 py-2 text-[13.5px] text-ink outline-none placeholder:text-muted focus:border-signal focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--signal)_20%,transparent)]";
const EMPTY: AgentInput = { name: "", role: "research", system_prompt: "", tier_pin: null, model_pin: null };

function msg(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : fallback;
}

export function AgentsView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { isAdmin, canWrite } = useWorkspace(workspaceId);
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string | null; draft: AgentInput } | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    listAgentsFull(workspaceId)
      .then(setAgents)
      .catch((e) => setError(msg(e, "Could not load agents")));
  }, [workspaceId]);
  useEffect(load, [load]);

  async function save() {
    if (!editing) return;
    setSaving(true);
    setError(null);
    try {
      if (editing.id) await updateAgent(workspaceId, editing.id, editing.draft);
      else await createAgent(workspaceId, editing.draft);
      setEditing(null);
      load();
    } catch (e) {
      setError(msg(e, "Could not save the agent"));
    } finally {
      setSaving(false);
    }
  }

  async function remove(agent: Agent) {
    if (!confirm(`Delete agent "${agent.name}"? Workflows that use it will fail.`)) return;
    try {
      await deleteAgent(workspaceId, agent.id);
      load();
    } catch (e) {
      setError(msg(e, "Could not delete the agent"));
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader
        eyebrow="Specialists"
        title={<>Your <em>agents</em></>}
        action={
          isAdmin && (
            <button className="btn-primary" onClick={() => setEditing({ id: null, draft: EMPTY })}>
              New agent
            </button>
          )
        }
      >
        Role-based specialists the router can call. Pin a tier or model, or leave both empty and let the gateway choose.
      </PageHeader>
      {error && <ErrorNote>{error}</ErrorNote>}

      {canWrite && <CoordinatorPanel workspaceId={workspaceId} />}

      {editing && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
          className="rise mt-6 grid gap-3 rounded-2xl border border-signal/40 bg-card p-5"
        >
          <p className="eyebrow">{editing.id ? "Edit agent" : "New agent"}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <input required maxLength={255} placeholder="Name" className={field} value={editing.draft.name}
              onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, name: e.target.value } })} />
            <select className={field} value={editing.draft.role}
              onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, role: e.target.value } })}>
              {AGENT_ROLES.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          <textarea rows={5} placeholder="System prompt" className={field} value={editing.draft.system_prompt}
            onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, system_prompt: e.target.value } })} />
          <div className="grid gap-3 sm:grid-cols-2">
            <select className={field} value={editing.draft.tier_pin ?? ""}
              onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, tier_pin: e.target.value || null } })}>
              <option value="">Tier: auto</option>
              {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input placeholder="Model pin, e.g. groq:llama-3.3-70b (optional)" className={field}
              value={editing.draft.model_pin ?? ""}
              onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, model_pin: e.target.value || null } })} />
          </div>
          <div className="flex gap-2">
            <button disabled={saving} className="btn-primary">{saving ? "Saving…" : "Save agent"}</button>
            <button type="button" className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </form>
      )}

      {agents === null && !error && <SkeletonRows n={3} />}
      {agents?.length === 0 && !editing && (
        <EmptyState icon={<span className="text-2xl">◎</span>} title={<>No agents <em>yet</em></>}>
          Built-in specialists still run in the coordinator. Create your own to customise prompts and models.
        </EmptyState>
      )}
      <ul className="mt-6 grid gap-3">
        {agents?.map((a) => (
          <AgentCard key={a.id} agent={a} workspaceId={workspaceId} isAdmin={isAdmin} canWrite={canWrite}
            onEdit={() => setEditing({ id: a.id, draft: { name: a.name, role: a.role, system_prompt: a.system_prompt, tier_pin: a.tier_pin, model_pin: a.model_pin } })}
            onDelete={() => void remove(a)} />
        ))}
      </ul>
    </div>
  );
}

function AgentCard({
  agent, workspaceId, isAdmin, canWrite, onEdit, onDelete,
}: { agent: Agent; workspaceId: string; isAdmin: boolean; canWrite: boolean; onEdit: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AgentRunResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      setResult(await runAgent(workspaceId, agent.id, input));
    } catch (e) {
      setErr(msg(e, "Run failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="step-in rounded-2xl border border-line-strong bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[16px] font-medium tracking-tight">{agent.name}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[11px] text-muted">
            <span className="rounded-full bg-signal-soft px-2 py-0.5 uppercase tracking-[0.12em] text-signal">{agent.role}</span>
            <span>{agent.model_pin ?? (agent.tier_pin ? `tier ${agent.tier_pin}` : "auto-routed")}</span>
          </p>
        </div>
        <div className="flex gap-2 text-[13px]">
          {canWrite && <button className="btn-ghost !px-3 !py-1.5" onClick={() => setOpen((o) => !o)}>{open ? "Close" : "Run"}</button>}
          {isAdmin && <button className="btn-ghost !px-3 !py-1.5" onClick={onEdit}>Edit</button>}
          {isAdmin && <button className="btn-ghost !px-3 !py-1.5 !text-fail" onClick={onDelete}>Delete</button>}
        </div>
      </div>
      {agent.system_prompt && <p className="mt-3 line-clamp-2 text-[13px] leading-6 text-ink-2">{agent.system_prompt}</p>}
      {open && (
        <div className="mt-4 grid gap-3 border-t border-line pt-4">
          <textarea rows={3} className={field} placeholder="Input for this agent" value={input} onChange={(e) => setInput(e.target.value)} />
          <div><button disabled={busy || !input.trim()} className="btn-primary" onClick={() => void run()}>{busy ? "Running…" : "Run agent"}</button></div>
          {err && <ErrorNote>{err}</ErrorNote>}
          {result && <RunOutput output={result.output} status={result.status} meta={`${result.llm_calls} LLM call(s) · ${result.models_used.join(", ")}`}
            steps={result.steps.map((s) => `${s.tool}(${JSON.stringify(s.arguments)}) → ${s.result}`)} />}
        </div>
      )}
    </li>
  );
}

function RunOutput({ output, status, meta, steps }: { output: string; status: string; meta: string; steps: string[] }) {
  return (
    <div className="rounded-xl bg-paper-2 p-4">
      <div className="flex items-center justify-between"><StatusBadge status={status} /><span className="font-mono text-[11px] text-muted">{meta}</span></div>
      {steps.length > 0 && (
        <ul className="mt-3 grid gap-1 font-mono text-[11.5px] text-ink-2">{steps.map((s, i) => <li key={i} className="truncate">⚙ {s}</li>)}</ul>
      )}
      <p className="mt-3 whitespace-pre-wrap text-[13.5px] leading-6">{output}</p>
    </div>
  );
}

function CoordinatorPanel({ workspaceId }: { workspaceId: string }) {
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CoordinatorResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      setResult(await runCoordinator(workspaceId, goal));
    } catch (e) {
      setErr(msg(e, "Coordinator failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-6 rounded-2xl border border-line-strong bg-card p-5">
      <p className="eyebrow">Coordinator</p>
      <p className="mt-1 text-[13.5px] text-muted">Give one goal. The coordinator plans it, hands each step to the matching specialist, and merges the result.</p>
      <textarea rows={2} className={`${field} mt-3`} placeholder="e.g. Research our competitors' pricing and write a one-page summary" value={goal} onChange={(e) => setGoal(e.target.value)} />
      <button disabled={busy || !goal.trim()} className="btn-primary mt-3" onClick={() => void run()}>{busy ? "Planning and running…" : "Run coordinator"}</button>
      {err && <ErrorNote>{err}</ErrorNote>}
      {result && (
        <div className="mt-4 grid gap-3">
          <ol className="grid gap-2">
            {result.steps.map((s, i) => (
              <li key={i} className="rounded-xl border border-line bg-paper p-3">
                <p className="flex items-center justify-between font-mono text-[11px] text-muted">
                  <span>{i + 1}. {s.role} · {s.agent}</span><StatusBadge status={s.status} />
                </p>
                <p className="mt-1 text-[13px] text-ink-2">{s.task}</p>
                <p className="mt-2 whitespace-pre-wrap text-[13px] leading-6">{s.output}</p>
              </li>
            ))}
          </ol>
          <RunOutput output={result.final} status={result.status} meta={`${result.llm_calls} LLM call(s)`} steps={[]} />
        </div>
      )}
    </section>
  );
}
