"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, deleteDocument, listDocuments, uploadDocument } from "@/lib/api";
import type { DocumentStatus, KnowledgeDocument } from "@/types";

const STATUS_STYLE: Record<DocumentStatus, string> = {
  pending: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  processing: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  ready: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
};

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

  return (
    <div className="mx-auto w-full max-w-3xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
            Documents
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Upload .txt, .md or .pdf files (up to 5 MB). Once a file is{" "}
            <em>ready</em>, chat can answer questions about it with citations.
          </p>
        </div>
        <label
          className={`shrink-0 cursor-pointer rounded-md bg-black px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200 ${
            uploading ? "pointer-events-none opacity-60" : ""
          }`}
        >
          {uploading ? "Uploading…" : "Upload"}
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".txt,.md,.pdf"
            className="hidden"
            onChange={(e) => void onFiles(e.target.files)}
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      {loading ? (
        <p className="mt-8 text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
      ) : docs.length === 0 ? (
        <p className="mt-8 rounded-md border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
          No documents yet. Upload one to get started.
        </p>
      ) : (
        <ul className="mt-6 grid gap-2">
          {docs.map((doc) => (
            <li
              key={doc.id}
              className="flex items-center justify-between gap-3 rounded-md border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-black dark:text-zinc-100">
                  {doc.filename}
                </p>
                <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                  {formatSize(doc.size_bytes)} ·{" "}
                  {new Date(doc.created_at).toLocaleString()}
                </p>
                {doc.status === "failed" && doc.error_message && (
                  <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                    {doc.error_message}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[doc.status]}`}
                >
                  {doc.status}
                </span>
                <button
                  onClick={() => void onDelete(doc)}
                  className="text-sm text-zinc-500 hover:text-red-600 dark:text-zinc-400 dark:hover:text-red-400"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
