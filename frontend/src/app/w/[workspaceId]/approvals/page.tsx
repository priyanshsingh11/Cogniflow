import { Suspense } from "react";
import { ApprovalsView } from "./approvals-view";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}>
      <ApprovalsView />
    </Suspense>
  );
}
