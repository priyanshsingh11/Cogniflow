import { Suspense } from "react";
import { KnowledgeView } from "./knowledge-view";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <KnowledgeView />
    </Suspense>
  );
}
