import { Suspense } from "react";
import { AgentsView } from "./agents-view";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <AgentsView />
    </Suspense>
  );
}
