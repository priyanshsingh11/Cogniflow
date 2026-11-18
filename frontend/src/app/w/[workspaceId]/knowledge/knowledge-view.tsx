"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { ErrorNote, PageHeader } from "@/components/page-header";
import { ApiError, askKnowledge, searchKnowledge } from "@/lib/api";
import type { AskResult, Passage } from "@/types";

const field =
  "w-full rounded-lg border border-line-strong bg-paper px-3.5 py-2.5 text-[14px] text-ink outline-none placeholder:text-muted focus:border-signal focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--signal)_20%,transparent)]";

function PassageList({ passages }: { passages: Passage[] }) {
  return (
    <ul className="mt-3 grid gap-2">
      {passages.map((p, i) => (
        <li key={`${p.document_id}-${p.chunk_index}-${i}`} className="rounded-xl border border-line-strong bg-card p-4">
          <p className="flex justify-between font-mono text-[11px] text-muted">
            <span>{p.filename} · chunk {p.chunk_index}</span><span>score {p.score.toFixed(3)}</span>
          </p>
          <p className="mt-2 whitespace-pre-wrap text-[13px] leading-6 text-ink-2">{p.content}</p>
        </li>
      ))}
    </ul>
  );
}

export function KnowledgeView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"search" | "ask">("ask");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [passages, setPassages] = useState<Passage[] | null>(null);
  const [answer, setAnswer] = useState<AskResult | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setPassages(null);
    setAnswer(null);
    try {
      if (mode === "ask") setAnswer(await askKnowledge(workspaceId, query));
      else setPassages((await searchKnowledge(workspaceId, query)).passages);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader eyebrow="Retrieval" title={<>Knowledge <em>search</em></>}>
        Query your uploaded documents directly. Search shows the raw matching passages; Ask has a model answer from them with citations.
      </PageHeader>
      <form onSubmit={(e) => void run(e)} className="mt-6 grid gap-3">
        <div className="flex gap-1 text-[13px]">
          {(["ask", "search"] as const).map((m) => (
            <button key={m} type="button" onClick={() => setMode(m)} className={`rounded-lg px-3 py-1.5 ${mode === m ? "bg-ink text-paper" : "text-ink-2 hover:bg-paper-2"}`}>
              {m === "ask" ? "Ask" : "Search passages"}
            </button>
          ))}
        </div>
        <input required className={field} placeholder={mode === "ask" ? "Ask a question about your documents…" : "Search phrase…"} value={query} onChange={(e) => setQuery(e.target.value)} />
        <div><button disabled={busy || !query.trim()} className="btn-primary">{busy ? "Working…" : mode === "ask" ? "Ask" : "Search"}</button></div>
      </form>
      {error && <ErrorNote>{error}</ErrorNote>}
      {answer && (
        <div className="mt-6">
          <div className="rounded-2xl border border-line-strong bg-card p-5">
            <p className="whitespace-pre-wrap text-[14.5px] leading-7">{answer.answer}</p>
            <p className="mt-3 font-mono text-[11px] text-muted">tier {answer.tier} · {answer.route_reason}</p>
          </div>
          <h2 className="eyebrow mt-6">Citations</h2>
          <PassageList passages={answer.citations} />
        </div>
      )}
      {passages && (passages.length ? <PassageList passages={passages} /> : <p className="mt-6 text-[13.5px] text-muted">No matching passages.</p>)}
    </div>
  );
}
