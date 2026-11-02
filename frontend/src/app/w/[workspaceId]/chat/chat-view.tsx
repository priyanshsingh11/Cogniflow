"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  createConversation,
  listConversations,
  listMessages,
  sendMessage,
} from "@/lib/api";
import type { ChatMessage, Conversation, Passage } from "@/types";

function CitationList({ citations }: { citations: Passage[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (citations.length === 0) return null;
  return (
    <div className="mt-3 border-t border-zinc-200 pt-2 dark:border-zinc-700">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Sources
      </p>
      <ul className="mt-1 grid gap-1">
        {citations.map((c, i) => (
          <li key={`${c.document_id}-${c.chunk_index}`} className="text-xs">
            <button
              onClick={() => setOpen(open === i ? null : i)}
              className="text-left text-zinc-700 underline-offset-2 hover:underline dark:text-zinc-300"
            >
              [{i + 1}] {c.filename} · passage {c.chunk_index + 1} · {Math.round(c.score * 100)}%
            </button>
            {open === i && (
              <p className="mt-1 whitespace-pre-wrap rounded bg-zinc-100 p-2 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                {c.content}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-4 py-2.5 text-sm ${
          isUser
            ? "bg-black text-white dark:bg-zinc-50 dark:text-black"
            : "border border-zinc-200 bg-white text-zinc-900 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100"
        }`}
      >
        <p className="whitespace-pre-wrap">
          {message.content ?? "(this message could not be recovered)"}
        </p>
        {!isUser && <CitationList citations={message.citations} />}
        {!isUser && message.meta?.tier && (
          <p className="mt-2 text-xs text-zinc-400">answered by {message.meta.tier} tier</p>
        )}
      </div>
    </div>
  );
}

export function ChatView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // No conversation selected means an empty thread (no state reset needed).
  const shownMessages = activeId ? messages : [];

  useEffect(() => {
    let cancelled = false;
    listConversations(workspaceId)
      .then((list) => {
        if (cancelled) return;
        setConversations(list);
        setActiveId((current) => current ?? list[0]?.id ?? null);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load conversations");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    listMessages(workspaceId, activeId)
      .then((m) => {
        if (!cancelled) setMessages(m);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load messages");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function newConversation() {
    setError(null);
    try {
      const conv = await createConversation(workspaceId, "New chat");
      setConversations((prev) => [conv, ...prev]);
      setActiveId(conv.id);
      setMessages([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create conversation");
    }
  }

  async function onSend(e: React.FormEvent) {
    e.preventDefault();
    const content = draft.trim();
    if (!content || sending) return;
    setError(null);
    setSending(true);
    try {
      let conversationId = activeId;
      if (!conversationId) {
        const conv = await createConversation(workspaceId, content.slice(0, 60));
        setConversations((prev) => [conv, ...prev]);
        setActiveId(conv.id);
        conversationId = conv.id;
      }
      const turn = await sendMessage(workspaceId, conversationId, content);
      setMessages((prev) => [...prev, turn.user_message, turn.assistant_message]);
      setDraft("");
    } catch (err) {
      // 400 = nothing indexed yet; 502 = every free model failed. Keep the draft.
      setError(err instanceof ApiError ? err.message : "Could not send the message");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 gap-6">
      <aside className="hidden w-52 shrink-0 flex-col gap-2 md:flex">
        <button
          onClick={() => void newConversation()}
          className="rounded-md bg-black px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
        >
          New chat
        </button>
        <ul className="grid grid-cols-[minmax(0,1fr)] gap-1">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setActiveId(c.id)}
                className={`w-full truncate rounded-md px-3 py-1.5 text-left text-sm ${
                  c.id === activeId
                    ? "bg-zinc-200 font-medium text-black dark:bg-zinc-800 dark:text-zinc-50"
                    : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
                }`}
              >
                {c.title || "Untitled"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Chat
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Answers come from your uploaded documents and cite their sources.
        </p>

        <div className="mt-4 flex min-h-[20rem] flex-1 flex-col gap-3 overflow-y-auto">
          {shownMessages.length === 0 && (
            <p className="m-auto text-sm text-zinc-500 dark:text-zinc-400">
              Ask a question about your documents.
            </p>
          )}
          {shownMessages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {sending && (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Thinking…</p>
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        <form onSubmit={onSend} className="mt-3 flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about your documents…"
            maxLength={20000}
            className="min-w-0 flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-black outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
          <button
            type="submit"
            disabled={sending || !draft.trim()}
            className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
          >
            Send
          </button>
        </form>
      </section>
    </div>
  );
}
