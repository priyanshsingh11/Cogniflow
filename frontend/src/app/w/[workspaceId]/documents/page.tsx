import { Suspense } from "react";
import { DocumentsView } from "./documents-view";

export default function Page() {
  return (
    <Suspense
      fallback={<p className="text-sm text-muted">Loading…</p>}
    >
      <DocumentsView />
    </Suspense>
  );
}
