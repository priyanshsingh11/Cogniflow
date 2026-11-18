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
import { ErrorNote, Icon } from "@/components/page-header";
import type { ChatMessage, Conversation, Passage } from "@/types";

const SUGGESTIONS = [
  "Summarize the key points of my documents",
  "What are the main risks mentioned?",
  "List any deadlines or dates",
];

/** Turn "[1]" markers in an answer into small signal chips. */
function withCitationChips(text: string) {
  return text.split(/(\[\d+\])/g).map((part, i) =>
    /^\[\d+\]$/.test(part) ? (
      <sup key={i} className="mx-0.5 rounded bg-signal-soft px-1 font-mono text-[10px] text-signal">
        {part.slice(1, -1)}
      </sup>
    ) : (
      part
    ),
  );
}

function CitationList({ citations }: { citations: Passage[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (citations.length === 0) return null;
  return (
    <div className="mt-3 border-t border-line pt-3">
      <p className="eyebrow !text-[10px]">Sources</p>
      <ul className="mt-2 grid gap-1.5">
        {citations.map((c, i) => (
          <li key={`${c.document_id}-${c.chunk_index}`}>
            <button
              onClick={() => setOpen(open === i ? null : i)}
              aria-expanded={open === i}
              className="flex w-full items-center gap-2 rounded-lg border border-line bg-paper px-2.5 py-1.5 text-left text-[12px] transition-colors hover:border-line-strong"
            >
              <span className="font-mono text-[11px] text-signal">[{i + 1}]</span>
              <span className="min-w-0 flex-1 truncate text-ink-2">
                {c.filename} · passage {c.chunk_index + 1}
              </span>
              <span className="font-mono text-[10.5px] text-muted">{Math.round(c.score * 100)}%</span>
            </button>
            {open === i && (
              <p className="step-in mt-1 whitespace-pre-wrap rounded-lg border-l-2 border-signal bg-paper-2/60 p-3 text-[12.5px] leading-5 text-ink-2">
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
  const text = message.content ?? "(this message could not be recovered)";
  return (
    <div className={`step-in flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[88%] px-4 py-3 text-[14px] leading-6 ${
          isUser
            ? "rounded-2xl rounded-br-md bg-ink text-paper"
            : "rounded-2xl rounded-bl-md border border-line-strong bg-card text-ink"
        }`}
      >
        <p className="whitespace-pre-wrap">{isUser ? text : withCitationChips(text)}</p>
        {!isUser && <CitationList citations={message.citations} />}
        {!isUser && message.meta?.tier && (
          <p className="mt-2 font-mono text-[10.5px] text-muted">answered by {message.meta.tier} tier</p>
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
    <div className="mx-auto flex w-full max-w-5xl flex-1 gap-6 md:h-[calc(100vh-4rem)]">
      <aside className="hidden w-56 shrink-0 flex-col gap-3 md:flex">
        <button onClick={() => void newConversation()} className="btn-primary justify-center">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          New chat
        </button>
        <p className="eyebrow !text-[10px] px-1">Conversations</p>
        <ul className="-mt-1 grid min-h-0 grid-cols-[minmax(0,1fr)] content-start gap-1 overflow-y-auto">
          {conversations.length === 0 && <li className="px-1 text-[12.5px] text-muted">None yet.</li>}
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setActiveId(c.id)}
                className={`relative w-full truncate rounded-lg px-3 py-2 text-left text-[13px] transition-colors ${
                  c.id === activeId ? "bg-card font-medium text-ink ring-1 ring-line-strong" : "text-ink-2 hover:bg-paper-2"
                }`}
              >
                {c.id === activeId && <span className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r bg-signal" />}
                {c.title || "Untitled"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="rise border-b border-line pb-4">
          <p className="eyebrow">Ask</p>
          <h1 className="display mt-1.5 text-4xl leading-none">Chat with your <em>documents</em></h1>
        </header>

        <div className="flex min-h-[20rem] flex-1 flex-col gap-4 overflow-y-auto py-5">
          {shownMessages.length === 0 && (
            <div className="m-auto max-w-md text-center">
              <div className="float-y mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-line-strong bg-paper text-signal">
                <Icon name="chat" />
              </div>
              <p className="display mt-5 text-3xl leading-tight">Ask anything, get <em>cited</em> answers</p>
              <p className="mt-2 text-[13.5px] leading-6 text-muted">Answers come only from your uploaded documents.</p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((q) => (
                  <button key={q} onClick={() => setDraft(q)} className="rounded-full border border-line-strong bg-card px-3.5 py-1.5 text-[12.5px] text-ink-2 transition-colors hover:border-signal hover:text-signal">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {shownMessages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {sending && (
            <div className="flex items-center gap-1.5 px-2" aria-label="Thinking">
              {[0, 1, 2].map((i) => (
                <span key={i} className="typing-dot h-1.5 w-1.5 rounded-full bg-signal" style={{ animationDelay: `${i * 160}ms` }} />
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && <ErrorNote>{error}</ErrorNote>}

        <form onSubmit={onSend} className="mt-3 flex items-center gap-2 rounded-2xl border border-line-strong bg-card p-1.5 pl-4 transition-shadow focus-within:border-signal focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--signal)_20%,transparent)]">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about your documents…"
            maxLength={20000}
            className="min-w-0 flex-1 bg-transparent py-2 text-[14px] text-ink outline-none placeholder:text-muted"
          />
          <button
            type="submit"
            disabled={sending || !draft.trim()}
            aria-label="Send"
            className="grid h-9 w-9 place-items-center rounded-xl bg-ink text-paper transition-colors hover:bg-signal hover:text-signal-ink disabled:opacity-40 disabled:hover:bg-ink disabled:hover:text-paper"
          >
            <svg width="15" height="15" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M7 12V2.5M3 6l4-4 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
        </form>
      </section>
    </div>
  );
}
