const NEUTRAL = "bg-paper-2 text-muted";
const STYLES: Record<string, string> = {
  queued: NEUTRAL,
  pending: NEUTRAL,
  running: "bg-info-soft text-info",
  waiting_approval: "bg-wait-soft text-wait",
  succeeded: "bg-ok-soft text-ok",
  approved: "bg-ok-soft text-ok",
  failed: "bg-fail-soft text-fail",
  rejected: "bg-fail-soft text-fail",
  cancelled: "bg-paper-2 text-muted line-through",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 font-mono text-[11px] ${
        STYLES[status] ?? STYLES.queued
      }`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

/** Runs that are still moving: the UI polls these until they settle. */
export function isActiveRun(status: string): boolean {
  return status === "queued" || status === "running";
}
