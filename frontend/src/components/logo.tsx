/**
 * Cogniflow mark: an open "C" ring (cognition) whose two ends are nodes joined
 * by a flow line. Ink node = where a run starts, signal node = where it is now.
 */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="var(--ink)" />
      <path
        d="M21.2 10.6A8 8 0 1 0 21.2 21.4"
        stroke="var(--paper)"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path d="M21.2 10.6h0" stroke="var(--paper)" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="22.6" cy="16" r="2.9" fill="var(--signal)" />
      <path d="M16 16h3.4" stroke="var(--signal)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className="text-[17px] font-semibold tracking-[-0.03em] text-ink">
        cogni<span className="display text-[20px] italic tracking-normal">flow</span>
      </span>
    </span>
  );
}
