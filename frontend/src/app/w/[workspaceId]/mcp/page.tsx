import { Suspense } from "react";
import { McpView } from "./mcp-view";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <McpView />
    </Suspense>
  );
}
