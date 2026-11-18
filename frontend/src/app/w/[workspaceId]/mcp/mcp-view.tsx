"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorNote, PageHeader, SkeletonRows } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import {
  ApiError,
  createMcpServer,
  deleteMcpServer,
  discoverMcpServer,
  listMcpServers,
  listMcpToolsFull,
  listToolCalls,
  patchMcpTool,
} from "@/lib/api";
import { useWorkspace } from "@/lib/use-role";
import type { McpServer, McpTool, McpToolCall } from "@/types";

const field =
  "w-full rounded-lg border border-line-strong bg-paper px-3.5 py-2 text-[13.5px] text-ink outline-none placeholder:text-muted focus:border-signal focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--signal)_20%,transparent)]";

function msg(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : fallback;
}

/** "KEY=value" lines -> object (headers for http, env for stdio). */
function parsePairs(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const i = line.indexOf("=");
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return out;
}

export function McpView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { isAdmin, canWrite } = useWorkspace(workspaceId);
  const [servers, setServers] = useState<McpServer[] | null>(null);
  const [tools, setTools] = useState<McpTool[]>([]);
  const [calls, setCalls] = useState<McpToolCall[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([listMcpServers(workspaceId), listMcpToolsFull(workspaceId), listToolCalls(workspaceId, 20)])
      .then(([s, t, c]) => {
        setServers(s);
        setTools(t);
        setCalls(c);
      })
      .catch((e) => setError(msg(e, "Could not load MCP data")));
  }, [workspaceId]);
  useEffect(load, [load]);

  async function act(id: string, fn: () => Promise<unknown>, fallback: string) {
    setBusy(id);
    setError(null);
    try {
      await fn();
      load();
    } catch (e) {
      setError(msg(e, fallback));
      load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader
        eyebrow="Tools"
        title={<>MCP <em>servers</em></>}
        action={isAdmin && <button className="btn-primary" onClick={() => setAdding((a) => !a)}>{adding ? "Close" : "Register server"}</button>}
      >
        Connect Model Context Protocol servers, discover their tools, then approve the ones agents and workflows may call.
      </PageHeader>
      {error && <ErrorNote>{error}</ErrorNote>}
      {adding && <AddServer workspaceId={workspaceId} onDone={() => { setAdding(false); load(); }} />}

      {servers === null && !error && <SkeletonRows n={2} />}
      {servers?.length === 0 && !adding && (
        <EmptyState icon={<span className="text-2xl">⌘</span>} title={<>No servers <em>connected</em></>}>
          Register a stdio command or an HTTP endpoint, then run discovery to import its tools.
        </EmptyState>
      )}

      <ul className="mt-6 grid gap-4">
        {servers?.map((s) => {
          const own = tools.filter((t) => t.server_id === s.id);
          return (
            <li key={s.id} className="step-in rounded-2xl border border-line-strong bg-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 text-[16px] font-medium tracking-tight">{s.name} <StatusBadge status={s.status} /></p>
                  <p className="mt-1 truncate font-mono text-[11.5px] text-muted">
                    {s.transport} · {s.url_or_command}{s.args?.length ? ` ${s.args.join(" ")}` : ""}{s.has_credentials ? " · 🔒 credentials" : ""}
                  </p>
                  {s.last_error && <p className="mt-1 text-[12px] text-fail">{s.last_error}</p>}
                </div>
                <div className="flex gap-2 text-[13px]">
                  {canWrite && <button disabled={busy === s.id} className="btn-ghost !px-3 !py-1.5" onClick={() => void act(s.id, () => discoverMcpServer(workspaceId, s.id), "Discovery failed")}>{busy === s.id ? "Working…" : "Discover tools"}</button>}
                  {isAdmin && <button className="btn-ghost !px-3 !py-1.5 !text-fail" onClick={() => confirm(`Remove "${s.name}" and its tools?`) && void act(s.id, () => deleteMcpServer(workspaceId, s.id), "Could not delete")}>Delete</button>}
                </div>
              </div>
              {own.length > 0 && (
                <ul className="mt-4 divide-y divide-line rounded-xl border border-line bg-paper">
                  {own.map((t) => (
                    <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <p className="font-mono text-[12.5px] text-ink">{t.name}{!t.active && <span className="ml-2 text-muted">(retired)</span>}</p>
                        {t.description && <p className="mt-0.5 line-clamp-1 text-[12px] text-muted">{t.description}</p>}
                      </div>
                      <div className="flex gap-4 text-[12.5px]">
                        <label className="flex items-center gap-1.5">
                          <input type="checkbox" disabled={!isAdmin} checked={t.approved} onChange={(e) => void act(t.id, () => patchMcpTool(workspaceId, t.id, { approved: e.target.checked }), "Could not update tool")} /> approved
                        </label>
                        <label className="flex items-center gap-1.5">
                          <input type="checkbox" disabled={!isAdmin} checked={t.requires_approval} onChange={(e) => void act(t.id, () => patchMcpTool(workspaceId, t.id, { requires_approval: e.target.checked }), "Could not update tool")} /> needs human approval
                        </label>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      {calls.length > 0 && (
        <>
          <h2 className="eyebrow mt-12">Recent tool calls</h2>
          <ul className="mt-3 grid gap-2">
            {calls.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 rounded-xl border border-line-strong bg-card px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate font-mono text-[12.5px]">{c.tool_name}</p>
                  <p className="font-mono text-[11px] text-muted">{c.invoked_by} · {c.latency_ms} ms · {new Date(c.created_at).toLocaleString()}</p>
                </div>
                <StatusBadge status={c.status} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function AddServer({ workspaceId, onDone }: { workspaceId: string; onDone: () => void }) {
  const [transport, setTransport] = useState<"stdio" | "http">("http");
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [args, setArgs] = useState("");
  const [secrets, setSecrets] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const pairs = parsePairs(secrets);
    const hasSecrets = Object.keys(pairs).length > 0;
    try {
      await createMcpServer(workspaceId, {
        name,
        transport,
        ...(transport === "http" ? { url: target } : { command: target, args: args.split(/\s+/).filter(Boolean) }),
        ...(hasSecrets ? { credentials: transport === "http" ? { headers: pairs } : { env: pairs } } : {}),
      });
      onDone();
    } catch (e2) {
      setErr(msg(e2, "Could not register the server"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="rise mt-6 grid gap-3 rounded-2xl border border-signal/40 bg-card p-5">
      <p className="eyebrow">Register server</p>
      <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
        <input required className={field} placeholder="Name (letters, numbers, spaces, - _)" value={name} onChange={(e) => setName(e.target.value)} />
        <select className={field} value={transport} onChange={(e) => setTransport(e.target.value as "stdio" | "http")}>
          <option value="http">http</option><option value="stdio">stdio</option>
        </select>
      </div>
      <input required className={field} placeholder={transport === "http" ? "https://server.example.com/mcp" : "Command, e.g. uvx"} value={target} onChange={(e) => setTarget(e.target.value)} />
      {transport === "stdio" && <input className={field} placeholder="Arguments, space separated" value={args} onChange={(e) => setArgs(e.target.value)} />}
      <textarea rows={2} className={field} placeholder={transport === "http" ? "Optional headers, one per line:\nAuthorization=Bearer …" : "Optional env vars, one per line:\nAPI_KEY=…"} value={secrets} onChange={(e) => setSecrets(e.target.value)} />
      <p className="text-[12px] text-muted">Credentials are encrypted at rest and never shown again.</p>
      {err && <ErrorNote>{err}</ErrorNote>}
      <div><button disabled={busy} className="btn-primary">{busy ? "Saving…" : "Register"}</button></div>
    </form>
  );
}
