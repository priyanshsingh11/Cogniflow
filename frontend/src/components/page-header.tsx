import type { ReactNode } from "react";

/** Shared header for every workspace page: eyebrow, serif title, blurb, action slot. */
export function PageHeader({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="rise flex flex-wrap items-end justify-between gap-x-6 gap-y-4 border-b border-line pb-6">
      <div className="min-w-0 max-w-xl">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="display mt-2 text-4xl leading-none sm:text-5xl">{title}</h1>
        {children && <p className="mt-3 text-[14px] leading-6 text-muted">{children}</p>}
      </div>
      {action}
    </header>
  );
}

/** Small stat tile used in a strip under a page header. */
export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "signal" | "ok" }) {
  return (
    <div className="rounded-xl border border-line bg-card px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</p>
      <p className={`display mt-1 text-3xl leading-none tabular-nums ${tone === "signal" ? "text-signal" : tone === "ok" ? "text-ok" : ""}`}>
        {value}
      </p>
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="mt-5 rounded-lg border border-fail/30 bg-fail-soft px-3.5 py-2.5 text-[13px] text-fail">
      {children}
    </p>
  );
}

export function SkeletonRows({ n = 3 }: { n?: number }) {
  return (
    <ul className="mt-6 grid gap-2" aria-label="Loading">
      {Array.from({ length: n }, (_, i) => (
        <li key={i} className="shimmer h-16 rounded-xl border border-line bg-card" />
      ))}
    </ul>
  );
}

/** Centered empty state: icon tile, serif headline, hint, optional action. */
export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rise mt-8 rounded-2xl border border-dashed border-line-strong bg-card/50 px-6 py-14 text-center">
      <div className="float-y mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-line-strong bg-paper text-signal">
        {icon}
      </div>
      <p className="display mt-5 text-3xl leading-tight">{title}</p>
      {children && <p className="mx-auto mt-2 max-w-sm text-[13.5px] leading-6 text-muted">{children}</p>}
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}

/** Line icons, 24px, currentColor. */
export function Icon({ name }: { name: "flow" | "run" | "shield" | "chat" | "log" }) {
  const d: Record<string, string> = {
    flow: "M5 6h5v4H5zM14 14h5v4h-5zM10 8h2a2 2 0 0 1 2 2v4",
    run: "M7 5l12 7-12 7V5z",
    shield: "M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3zM9 12l2 2 4-4",
    chat: "M4 5h16v11H9l-5 4V5z",
    log: "M6 4h12v16H6zM9 9h6M9 13h6M9 17h3",
  };
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d={d[name]} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
