"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, deleteDocument, listDocuments, uploadDocument } from "@/lib/api";
import { PageHeader, Stat } from "@/components/page-header";
import type { DocumentStatus, KnowledgeDocument } from "@/types";

const STATUS_STYLE: Record<DocumentStatus, string> = {
  pending: "bg-paper-2 text-muted",
  processing: "bg-wait-soft text-wait",
  ready: "bg-ok-soft text-ok",
  failed: "bg-fail-soft text-fail",
};

function ext(name: string): string {
  const e = name.split(".").pop()?.toLowerCase() ?? "";
  return ["pdf", "md", "txt"].includes(e) ? e : "file";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const POLL_MS = 2000;

export function DocumentsView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [docs, setDocs] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setDocs(await listDocuments(workspaceId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load documents");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    let cancelled = false;
    listDocuments(workspaceId)
      .then((list) => {
        if (!cancelled) setDocs(list);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load documents");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  // Indexing happens in the background worker: poll while anything is unfinished.
  const hasUnfinished = docs.some((d) => d.status === "pending" || d.status === "processing");
  useEffect(() => {
    if (!hasUnfinished) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [hasUnfinished, refresh]);

  async function onFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setError(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        try {
          await uploadDocument(workspaceId, file);
        } catch (err) {
          setError(
            `${file.name}: ${err instanceof ApiError ? err.message : "upload failed"}`,
          );
        }
      }
      await refresh();
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function onDelete(doc: KnowledgeDocument) {
    if (!window.confirm(`Delete "${doc.filename}" and its indexed passages?`)) return;
    setError(null);
    try {
      await deleteDocument(workspaceId, doc.id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    }
  }

  const ready = docs.filter((d) => d.status === "ready").length;
  const indexing = docs.filter((d) => d.status === "pending" || d.status === "processing").length;
  const totalBytes = docs.reduce((n, d) => n + d.size_bytes, 0);

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader
        eyebrow="Knowledge"
        title={<>Your <em>documents</em></>}
        action={
          <label className={`btn-primary cursor-pointer ${uploading ? "pointer-events-none opacity-60" : ""}`}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M7 11V3M3.5 6.5L7 3l3.5 3.5M2 12h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
            {uploading ? "Uploading…" : "Upload"}
            <input ref={fileInput} type="file" multiple accept=".txt,.md,.pdf" className="hidden" onChange={(e) => void onFiles(e.target.files)} />
          </label>
        }
      >
        Chat and workflows answer from these files with citations. Once a file is <em>ready</em>, it is searchable.
      </PageHeader>

      {docs.length > 0 && (
        <div className="rise mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4" style={{ "--d": "80ms" } as React.CSSProperties}>
          <Stat label="Documents" value={docs.length} />
          <Stat label="Ready" value={ready} tone="ok" />
          <Stat label="Indexing" value={indexing} tone={indexing ? "signal" : undefined} />
          <Stat label="Stored" value={formatSize(totalBytes)} />
        </div>
      )}

      {error && (
        <p role="alert" className="mt-5 rounded-lg border border-fail/30 bg-fail-soft px-3.5 py-2.5 text-[13px] text-fail">{error}</p>
      )}

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); void onFiles(e.dataTransfer.files); }}
        className={`rise mt-6 rounded-2xl border border-dashed text-center transition-all ${
          dragging ? "border-signal bg-signal-soft" : "border-line-strong bg-card/50"
        } ${docs.length === 0 && !loading ? "px-6 py-14" : "px-4 py-5"}`}
        style={{ "--d": "140ms" } as React.CSSProperties}
      >
        {docs.length === 0 && !loading ? (
          <>
            <div className="float-y mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-line-strong bg-paper text-signal">
              <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true"><path d="M7 3h8l5 5v15H7V3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /><path d="M15 3v5h5M10.5 14h6M10.5 18h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </div>
            <p className="display mt-5 text-3xl leading-tight">Teach it your <em>knowledge</em></p>
            <p className="mx-auto mt-2 max-w-sm text-[13.5px] leading-6 text-muted">
              Drop .txt, .md or .pdf files here (up to 5 MB each), or use Upload.
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-2 font-mono text-[11px] text-ink-2">
              {["parse", "chunk", "embed", "searchable"].map((st, i, arr) => (
                <span key={st} className="flex items-center gap-2">
                  <span className="rounded-full border border-line-strong bg-card px-3 py-1">{st}</span>
                  {i < arr.length - 1 && <span className="text-signal">→</span>}
                </span>
              ))}
            </div>
          </>
        ) : (
          <p className="text-[13px] text-muted">
            {dragging ? "Release to upload" : "Drop more files here · .txt .md .pdf · up to 5 MB"}
          </p>
        )}
      </div>

      {loading ? (
        <ul className="mt-6 grid gap-2" aria-label="Loading documents">
          {[0, 1, 2].map((i) => <li key={i} className="shimmer h-16 rounded-xl border border-line bg-card" />)}
        </ul>
      ) : (
        docs.length > 0 && (
          <ul className="mt-6 grid gap-2">
            {docs.map((doc, i) => {
              const busy = doc.status === "pending" || doc.status === "processing";
              return (
                <li
                  key={doc.id}
                  className="step-in group relative overflow-hidden rounded-xl border border-line-strong bg-card transition-colors hover:border-ink-2"
                  style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
                >
                  <div className="flex items-center gap-4 px-4 py-3.5">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-line bg-paper font-mono text-[10.5px] font-medium uppercase text-ink-2">
                      {ext(doc.filename)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[14px] font-medium text-ink">{doc.filename}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-muted">
                        {formatSize(doc.size_bytes)} · {new Date(doc.created_at).toLocaleString()}
                      </p>
                      {doc.status === "failed" && doc.error_message && (
                        <p className="mt-1 text-[12px] text-fail">{doc.error_message}</p>
                      )}
                    </div>
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[11px] ${STATUS_STYLE[doc.status]}`}>
                      {busy && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-wait text-wait" />}
                      {doc.status}
                    </span>
                    <button
                      onClick={() => void onDelete(doc)}
                      aria-label={`Delete ${doc.filename}`}
                      className="rounded-md p-1.5 text-muted opacity-60 transition hover:bg-fail-soft hover:text-fail group-hover:opacity-100"
                    >
                      <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true"><path d="M2.5 4h10M6 4V2.5h3V4M4 4l.6 8h5.8L11 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    </button>
                  </div>
                  {busy && <div className="shimmer absolute inset-x-0 bottom-0 h-0.5" />}
                </li>
              );
            })}
          </ul>
        )
      )}
    </div>
  );
}
