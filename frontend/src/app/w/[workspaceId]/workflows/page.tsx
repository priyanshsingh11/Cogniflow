import { Suspense } from "react";
import { WorkflowsView } from "./workflows-view";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}>
      <WorkflowsView />
    </Suspense>
  );
}
