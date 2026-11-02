import { Suspense } from "react";
import { ChatView } from "./chat-view";

export default function Page() {
  return (
    <Suspense
      fallback={<p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}
    >
      <ChatView />
    </Suspense>
  );
}
