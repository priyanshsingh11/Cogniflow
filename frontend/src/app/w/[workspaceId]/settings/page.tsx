import { Suspense } from "react";
import { SettingsView } from "./settings-view";

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <SettingsView />
    </Suspense>
  );
}
