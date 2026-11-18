import Link from "next/link";
import { Logo } from "@/components/logo";

const QUOTES = [
  ["Cited", "Every answer links to the passages it used."],
  ["Resumable", "Runs pick up at the first unfinished step."],
  ["Auditable", "Every model attempt and change is recorded."],
];

/** Two-column auth layout: form on the left, a quiet brand panel on the right. */
export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid flex-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <Link href="/" aria-label="Cogniflow home" className="w-fit"><Logo /></Link>
        <main className="rise mx-auto my-auto w-full max-w-sm py-16">{children}</main>
        <p className="text-xs text-muted">© Cogniflow · AI workbench</p>
      </div>

      <aside className="relative hidden overflow-hidden bg-ink text-paper lg:block" aria-hidden="true">
        <div className="absolute inset-0 opacity-[0.16]" style={{ backgroundImage: "radial-gradient(currentColor 1px, transparent 1px)", backgroundSize: "22px 22px" }} />
        <svg className="absolute inset-0 h-full w-full text-signal" viewBox="0 0 400 600" preserveAspectRatio="xMidYMid slice">
          <path className="flow-dash" d="M-20 470 C 90 470, 110 300, 200 300 S 310 130, 430 130" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="200" cy="300" r="5" fill="currentColor" />
          <circle cx="200" cy="300" r="14" fill="none" stroke="currentColor" opacity="0.4" />
        </svg>
        <div className="relative flex h-full flex-col justify-end p-12">
          <h2 className="display max-w-sm text-5xl leading-[1.02]">
            See what your AI <em className="text-signal">actually did</em>.
          </h2>
          <ul className="mt-10 grid gap-4 border-t border-paper/15 pt-6">
            {QUOTES.map(([k, v]) => (
              <li key={k} className="flex gap-4 text-[13.5px]">
                <span className="w-20 shrink-0 font-mono text-[11px] uppercase tracking-[0.14em] text-signal">{k}</span>
                <span className="text-paper/65">{v}</span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}

export const inputCls =
  "w-full rounded-lg border border-line-strong bg-card px-3.5 py-2.5 text-sm text-ink outline-none transition-shadow placeholder:text-muted focus:border-signal focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--signal)_22%,transparent)]";
