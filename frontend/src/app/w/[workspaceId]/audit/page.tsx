import { Suspense } from "react";
import { AuditView } from "./audit-view";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}>
      <AuditView />
    </Suspense>
  );
}
