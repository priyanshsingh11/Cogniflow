"use client";

import { useEffect, useState } from "react";
import { listAgents, listMcpTools } from "@/lib/api";
import type { AgentSummary, McpToolSummary, StepInput, StepType, WorkflowStep } from "@/types";

const STEP_TYPES: { value: StepType; label: string; help: string }[] = [
  { value: "llm", label: "AI call", help: "Ask a model. Output: content" },
  { value: "knowledge_search", label: "Knowledge search", help: "Search uploaded documents. Output: passages, count" },
  { value: "mcp_tool", label: "MCP tool", help: "Call an approved tool. Output: tool result" },
  { value: "condition", label: "Condition", help: "Branch to another step" },
  { value: "agent", label: "Agent", help: "Run an agent with tools. Output: output" },
  { value: "coordinator", label: "Coordinator", help: "Plan and delegate a goal. Output: output" },
  { value: "approval", label: "Human approval", help: "Pause until a person approves" },
];

const OPERATORS = ["==", "!=", ">", ">=", "<", "<=", "contains", "not_empty", "is_empty"];
const NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

type Config = Record<string, unknown>;
type DraftStep = { key: string; name: string; type: StepType; config: Config };

const inputClass =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-black outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function str(config: Config, key: string): string {
  const v = config[key];
  return typeof v === "string" ? v : typeof v === "number" ? String(v) : "";
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium text-zinc-700 dark:text-zinc-300">{label}</span>
      {children}
      {hint && <span className="text-xs text-zinc-500 dark:text-zinc-400">{hint}</span>}
    </label>
  );
}

function newKey(): string {
  return crypto.randomUUID();
}

function toDraft(step: WorkflowStep): DraftStep {
  const config = { ...step.config };
  // The MCP arguments object is edited as JSON text.
  if (step.type === "mcp_tool" && typeof config.arguments === "object") {
    config.arguments = JSON.stringify(config.arguments, null, 2);
  }
  return { key: newKey(), name: step.name, type: step.type, config };
}

/** Validates the draft and converts it into the API payload, or returns an error. */
function buildPayload(steps: DraftStep[]): { steps: StepInput[] } | { error: string } {
  if (steps.length === 0) return { error: "Add at least one step." };
  const seen = new Set<string>();
  const out: StepInput[] = [];
  for (const [index, s] of steps.entries()) {
    const label = s.name || `Step ${index + 1}`;
    if (!NAME_PATTERN.test(s.name)) {
      return { error: `${label}: names use letters, digits and underscores, and cannot start with a digit (so templates like {{ steps.name.content }} work).` };
    }
    if (seen.has(s.name)) return { error: `Two steps are named "${s.name}".` };
    seen.add(s.name);

    const config: Config = {};
    for (const [k, v] of Object.entries(s.config)) {
      // "__" keys are UI-only state (e.g. the condition mode) and never reach the API.
      if (k.startsWith("__")) continue;
      if (v !== "" && v !== undefined && v !== null) config[k] = v;
    }
    for (const numeric of ["top_k", "max_steps", "timeout_seconds", "max_retries"]) {
      if (numeric in config) {
        const n = Number(config[numeric]);
        if (!Number.isFinite(n) || n < 0) return { error: `${label}: ${numeric} must be a number.` };
        config[numeric] = n;
      }
    }
    const need = (key: string, what: string) =>
      config[key] ? null : `${label}: ${what} is required.`;
    const missing =
      s.type === "llm" ? need("prompt", "the prompt")
      : s.type === "knowledge_search" ? need("query", "the query")
      : s.type === "mcp_tool" ? need("tool_id", "a tool")
      : s.type === "agent" ? need("agent_id", "an agent") ?? need("input", "the input")
      : s.type === "coordinator" ? need("goal", "the goal")
      : s.type === "condition"
        ? config.expression || (config.predicate as Config | undefined)?.field
          ? null
          : `${label}: give an expression or a field to compare.`
        : null;
    if (missing) return { error: missing };

    if (s.type === "mcp_tool" && typeof config.arguments === "string") {
      try {
        const parsed: unknown = JSON.parse(config.arguments);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error();
        config.arguments = parsed;
      } catch {
        return { error: `${label}: arguments must be a JSON object, e.g. {"a": 1}.` };
      }
    }
    out.push({ name: s.name, type: s.type, position: index, config });
  }
  return { steps: out };
}

export function WorkflowEditor({
  initialName = "",
  initialDescription = "",
  initialSteps = [],
  isNew,
  workspaceId,
  saving,
  onSave,
}: {
  initialName?: string;
  initialDescription?: string;
  initialSteps?: WorkflowStep[];
  isNew: boolean;
  workspaceId: string;
  saving: boolean;
  onSave: (value: { name: string; description: string; steps: StepInput[] }) => void;
}) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [steps, setSteps] = useState<DraftStep[]>(() => initialSteps.map(toDraft));
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [tools, setTools] = useState<McpToolSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listAgents(workspaceId)
      .then((list) => !cancelled && setAgents(list))
      .catch(() => undefined);
    listMcpTools(workspaceId)
      .then((list) => !cancelled && setTools(list.filter((t) => t.active && t.approved && !t.requires_approval)))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  function update(key: string, patch: Partial<DraftStep>) {
    setSteps((prev) => prev.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  }
  function setConfig(key: string, field: string, value: unknown) {
    setSteps((prev) =>
      prev.map((s) => (s.key === key ? { ...s, config: { ...s.config, [field]: value } } : s)),
    );
  }
  function addStep() {
    setSteps((prev) => [
      ...prev,
      { key: newKey(), name: `step_${prev.length + 1}`, type: "llm", config: {} },
    ]);
  }
  function move(index: number, delta: number) {
    setSteps((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }
  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (isNew && !name.trim()) return setError("Give the workflow a name.");
    const built = buildPayload(steps);
    if ("error" in built) return setError(built.error);
    onSave({ name: name.trim(), description: description.trim(), steps: built.steps });
  }

  return (
    <form onSubmit={submit} className="grid gap-5">
      {isNew && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} maxLength={255} />
          </Field>
          <Field label="Description (optional)">
            <input className={inputClass} value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
        </div>
      )}

      <p className="rounded-md bg-zinc-100 p-3 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
        Steps run in order. Use <code>{"{{ input.field }}"}</code> for the run input and{" "}
        <code>{"{{ steps.step_name.content }}"}</code> for an earlier step&apos;s output (each type lists its
        output fields below).
      </p>

      <ol className="grid gap-4">
        {steps.map((s, i) => {
          const others = steps.filter((o) => o.key !== s.key).map((o) => o.name);
          const meta = STEP_TYPES.find((t) => t.value === s.type);
          const predicate = (s.config.predicate as Config | undefined) ?? {};
          const useExpression = s.config.__mode !== "predicate" && !s.config.predicate;
          return (
            <li key={s.key} className="rounded-md border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
              <div className="flex flex-wrap items-end gap-3">
                <span className="pb-2 text-sm font-semibold text-zinc-500">{i + 1}</span>
                <div className="w-44">
                  <Field label="Name">
                    <input className={inputClass} value={s.name} onChange={(e) => update(s.key, { name: e.target.value })} />
                  </Field>
                </div>
                <div className="w-48">
                  <Field label="Type">
                    <select
                      className={inputClass}
                      value={s.type}
                      onChange={(e) => update(s.key, { type: e.target.value as StepType, config: {} })}
                    >
                      {STEP_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </Field>
                </div>
                <div className="ml-auto flex gap-1 pb-1 text-sm">
                  <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="rounded px-2 py-1 text-zinc-600 hover:bg-zinc-100 disabled:opacity-30 dark:text-zinc-300 dark:hover:bg-zinc-800" aria-label="Move up">↑</button>
                  <button type="button" onClick={() => move(i, 1)} disabled={i === steps.length - 1} className="rounded px-2 py-1 text-zinc-600 hover:bg-zinc-100 disabled:opacity-30 dark:text-zinc-300 dark:hover:bg-zinc-800" aria-label="Move down">↓</button>
                  <button type="button" onClick={() => setSteps((p) => p.filter((o) => o.key !== s.key))} className="rounded px-2 py-1 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950" aria-label="Remove step">Remove</button>
                </div>
              </div>
              {meta && <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{meta.help}</p>}

              <div className="mt-3 grid gap-3">
                {s.type === "llm" && (
                  <>
                    <Field label="Prompt">
                      <textarea className={inputClass} rows={4} value={str(s.config, "prompt")} onChange={(e) => setConfig(s.key, "prompt", e.target.value)} />
                    </Field>
                    <Field label="System prompt (optional)">
                      <textarea className={inputClass} rows={2} value={str(s.config, "system_prompt")} onChange={(e) => setConfig(s.key, "system_prompt", e.target.value)} />
                    </Field>
                    <Field label="Model tier" hint="Auto lets the router choose.">
                      <select className={inputClass} value={str(s.config, "tier")} onChange={(e) => setConfig(s.key, "tier", e.target.value)}>
                        <option value="">Auto</option>
                        <option value="small">Small</option>
                        <option value="medium">Medium</option>
                        <option value="large">Large</option>
                      </select>
                    </Field>
                  </>
                )}
                {s.type === "knowledge_search" && (
                  <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
                    <Field label="Query">
                      <input className={inputClass} value={str(s.config, "query")} onChange={(e) => setConfig(s.key, "query", e.target.value)} />
                    </Field>
                    <Field label="Top K">
                      <input className={inputClass} type="number" min={1} max={20} value={str(s.config, "top_k")} onChange={(e) => setConfig(s.key, "top_k", e.target.value)} placeholder="5" />
                    </Field>
                  </div>
                )}
                {s.type === "mcp_tool" && (
                  <>
                    <Field label="Tool" hint={tools.length === 0 ? "No approved tools yet. Register a server, run discovery and approve a tool first (API for now)." : undefined}>
                      <select className={inputClass} value={str(s.config, "tool_id")} onChange={(e) => setConfig(s.key, "tool_id", e.target.value)}>
                        <option value="">Select a tool…</option>
                        {tools.map((t) => (
                          <option key={t.id} value={t.id}>{t.server_name} / {t.name}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Arguments (JSON)">
                      <textarea className={`${inputClass} font-mono`} rows={3} value={str(s.config, "arguments")} onChange={(e) => setConfig(s.key, "arguments", e.target.value)} placeholder='{"a": 1}' />
                    </Field>
                  </>
                )}
                {s.type === "agent" && (
                  <>
                    <Field label="Agent" hint={agents.length === 0 ? "No agents in this workspace yet (create one via the API)." : undefined}>
                      <select className={inputClass} value={str(s.config, "agent_id")} onChange={(e) => setConfig(s.key, "agent_id", e.target.value)}>
                        <option value="">Select an agent…</option>
                        {agents.map((a) => (
                          <option key={a.id} value={a.id}>{a.name} ({a.role})</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Input">
                      <textarea className={inputClass} rows={3} value={str(s.config, "input")} onChange={(e) => setConfig(s.key, "input", e.target.value)} />
                    </Field>
                  </>
                )}
                {s.type === "coordinator" && (
                  <Field label="Goal">
                    <textarea className={inputClass} rows={3} value={str(s.config, "goal")} onChange={(e) => setConfig(s.key, "goal", e.target.value)} />
                  </Field>
                )}
                {s.type === "approval" && (
                  <Field label="Message for the approver" hint="Shown in the approval inbox. Templates work here too.">
                    <input className={inputClass} value={str(s.config, "description")} onChange={(e) => setConfig(s.key, "description", e.target.value)} />
                  </Field>
                )}
                {s.type === "condition" && (
                  <>
                    <div className="flex gap-4 text-sm">
                      <label className="flex items-center gap-1.5">
                        <input type="radio" checked={useExpression} onChange={() => { setConfig(s.key, "predicate", undefined); setConfig(s.key, "__mode", "expression"); }} />
                        Expression
                      </label>
                      <label className="flex items-center gap-1.5">
                        <input type="radio" checked={!useExpression} onChange={() => { setConfig(s.key, "expression", undefined); setConfig(s.key, "__mode", "predicate"); setConfig(s.key, "predicate", { field: "", op: "==", value: "" }); }} />
                        Compare a field
                      </label>
                    </div>
                    {useExpression ? (
                      <Field label="Expression" hint='True/false, e.g. {{ steps.search.count > 0 }}'>
                        <input className={inputClass} value={str(s.config, "expression")} onChange={(e) => setConfig(s.key, "expression", e.target.value)} />
                      </Field>
                    ) : (
                      <div className="grid gap-3 sm:grid-cols-[1fr_9rem_1fr]">
                        <Field label="Field" hint="e.g. steps.search.count">
                          <input className={inputClass} value={String(predicate.field ?? "")} onChange={(e) => setConfig(s.key, "predicate", { ...predicate, field: e.target.value })} />
                        </Field>
                        <Field label="Operator">
                          <select className={inputClass} value={String(predicate.op ?? "==")} onChange={(e) => setConfig(s.key, "predicate", { ...predicate, op: e.target.value })}>
                            {OPERATORS.map((op) => <option key={op} value={op}>{op}</option>)}
                          </select>
                        </Field>
                        <Field label="Value">
                          <input className={inputClass} value={String(predicate.value ?? "")} onChange={(e) => setConfig(s.key, "predicate", { ...predicate, value: e.target.value })} />
                        </Field>
                      </div>
                    )}
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field label="If true, go to" hint="Blank = the next step">
                        <select className={inputClass} value={str(s.config, "then_step")} onChange={(e) => setConfig(s.key, "then_step", e.target.value)}>
                          <option value="">Next step</option>
                          {others.map((n) => <option key={n} value={n}>{n}</option>)}
                        </select>
                      </Field>
                      <Field label="If false, go to" hint="Blank = the next step">
                        <select className={inputClass} value={str(s.config, "else_step")} onChange={(e) => setConfig(s.key, "else_step", e.target.value)}>
                          <option value="">Next step</option>
                          {others.map((n) => <option key={n} value={n}>{n}</option>)}
                        </select>
                      </Field>
                    </div>
                  </>
                )}

                <details className="text-sm">
                  <summary className="cursor-pointer text-zinc-500 dark:text-zinc-400">Timeout and retries</summary>
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    <Field label="Timeout (seconds)">
                      <input className={inputClass} type="number" min={1} value={str(s.config, "timeout_seconds")} onChange={(e) => setConfig(s.key, "timeout_seconds", e.target.value)} placeholder="60" />
                    </Field>
                    <Field label="Retries">
                      <input className={inputClass} type="number" min={0} max={5} value={str(s.config, "max_retries")} onChange={(e) => setConfig(s.key, "max_retries", e.target.value)} placeholder="0" />
                    </Field>
                  </div>
                </details>
              </div>
            </li>
          );
        })}
      </ol>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={addStep} className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900">
          + Add step
        </button>
        <button type="submit" disabled={saving} className="rounded-md bg-black px-4 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200">
          {saving ? "Saving…" : isNew ? "Create workflow" : "Save as new version"}
        </button>
        {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>
    </form>
  );
}

