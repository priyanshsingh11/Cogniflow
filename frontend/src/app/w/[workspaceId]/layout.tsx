import { Suspense } from "react";
import { WorkspaceShell } from "./workspace-shell";

// The shell reads the pathname/params at runtime, so it streams in behind Suspense.
export default function WorkspaceLayout({ children }: LayoutProps<"/w/[workspaceId]">) {
  return (
    <Suspense
      fallback={<p className="p-8 text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}
    >
      <WorkspaceShell>{children}</WorkspaceShell>
    </Suspense>
  );
}
