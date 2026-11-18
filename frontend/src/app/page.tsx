import Link from "next/link";
import { Logo } from "@/components/logo";
import { GatewayDemo } from "@/components/landing/gateway-demo";
import { HeroTrace } from "@/components/landing/hero-trace";
import { Reveal } from "@/components/landing/reveal";
import { UsageBars } from "@/components/landing/usage-bars";
import DepsStatus from "./deps-status";

const STACK = [
  "FastAPI", "Next.js", "PostgreSQL + pgvector", "MongoDB", "Redis", "arq", "LangGraph",
  "Model Context Protocol", "Groq", "OpenRouter", "fastembed",
];

const PHASES: [string, string, boolean][] = [
  ["0–2", "Foundations, auth, tenancy, LLM gateway, agents", true],
  ["3", "Knowledge: upload, embed, cited answers, chat", true],
  ["4", "MCP tools: discover, validate, invoke", true],
  ["5–6", "Durable workflow engine and human approvals", true],
  ["7", "Frontend: documents, chat, editor, runs, inbox", true],
  ["8", "Audit log, rate limits, usage dashboard", true],
  ["9", "Evaluation: datasets, cases, scores", false],
  ["10", "Visual builder, schedule and webhook triggers", false],
  ["11", "Deploy and polish", false],
];

function SectionHead({ eyebrow, title, children }: { eyebrow: string; title: React.ReactNode; children?: React.ReactNode }) {
  return (
    <Reveal className="max-w-2xl">
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="display mt-3 text-4xl leading-[1.05] sm:text-5xl">{title}</h2>
      {children && <p className="mt-4 text-[15px] leading-7 text-muted">{children}</p>}
    </Reveal>
  );
}

const panel = "rounded-2xl border border-line-strong bg-card";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col overflow-x-clip">
      {/* ───────── Nav ───────── */}
      <header className="sticky top-0 z-50 border-b border-line/70 bg-paper/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-5 sm:px-8">
          <Link href="/" aria-label="Cogniflow home"><Logo /></Link>
          <nav aria-label="Primary" className="hidden items-center gap-8 text-[13px] text-ink-2 md:flex">
            {[["#gateway", "Gateway"], ["#workflows", "Workflows"], ["#knowledge", "Knowledge"], ["#observe", "Observability"], ["#roadmap", "Roadmap"]].map(([h, l]) => (
              <a key={h} href={h} className="transition-colors hover:text-signal">{l}</a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/login" className="hidden px-3 py-2 text-[13px] font-medium text-ink-2 hover:text-ink sm:block">Sign in</Link>
            <Link href="/signup" className="btn-primary !px-4 !py-2 text-[13px]">Get started</Link>
          </div>
        </div>
      </header>

      {/* ───────── Hero ───────── */}
      <section className="relative">
        <div className="dot-grid fade-edges absolute inset-0 opacity-70" aria-hidden="true" />
        <div className="relative mx-auto grid w-full max-w-6xl items-center gap-14 px-5 pb-24 pt-16 sm:px-8 md:pt-24 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <p className="rise eyebrow inline-flex items-center gap-2 rounded-full border border-line-strong bg-card px-3 py-1.5 normal-case tracking-normal">
              <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-signal text-signal" />
              <span className="font-mono text-[11.5px] tracking-normal text-ink-2">Phases 0–8 shipped · 200 tests passing</span>
            </p>
            <h1 className="rise display mt-6 text-[3.1rem] leading-[0.98] sm:text-7xl lg:text-[5.4rem]" style={{ "--d": "80ms" } as React.CSSProperties}>
              AI workflows you can <em className="text-signal">actually</em> trust.
            </h1>
            <p className="rise mt-6 max-w-xl text-[16.5px] leading-8 text-ink-2" style={{ "--d": "180ms" } as React.CSSProperties}>
              Cogniflow chains agents, your documents and external tools into multi-step automations, then
              shows you exactly what happened: every step, tool call, model attempt, failure, latency and token.
              Not a chatbot wrapper. A workbench.
            </p>
            <div className="rise mt-9 flex flex-wrap gap-3" style={{ "--d": "280ms" } as React.CSSProperties}>
              <Link href="/signup" className="btn-primary">
                Create a workspace
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2 7h10M8 3l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </Link>
              <a href="#gateway" className="btn-ghost">See the gateway fail safely</a>
            </div>
            <dl className="rise mt-12 grid max-w-md grid-cols-3 gap-6 border-t border-line pt-6" style={{ "--d": "380ms" } as React.CSSProperties}>
              {[["7", "step types"], ["3", "model tiers"], ["4", "roles, 404 isolation"]].map(([n, l]) => (
                <div key={l}>
                  <dt className="display text-4xl leading-none">{n}</dt>
                  <dd className="mt-1.5 text-[12px] leading-4 text-muted">{l}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="rise" style={{ "--d": "260ms" } as React.CSSProperties}>
            <HeroTrace />
          </div>
        </div>
      </section>

      {/* ───────── Stack marquee ───────── */}
      <section aria-label="Built with" className="border-y border-line bg-paper-2/60 py-5">
        <div className="marquee-wrap overflow-hidden">
          <ul className="marquee flex w-max items-center gap-12 pr-12 font-mono text-[13px] text-muted">
            {[...STACK, ...STACK].map((s, i) => (
              <li key={i} className="flex items-center gap-12 whitespace-nowrap" aria-hidden={i >= STACK.length}>
                {s}
                <span className="text-signal">✦</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ───────── Gateway ───────── */}
      <section id="gateway" className="mx-auto w-full max-w-6xl px-5 py-24 sm:px-8 md:py-32">
        <div className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
          <div>
            <SectionHead
              eyebrow="01 · LLM gateway"
              title={<>Two kinds of failure. <em>Two</em> different fixes.</>}
            >
              Every model call goes through one door. When a provider is unhealthy it falls back sideways. When
              a call works but the answer is unusable, it escalates up to a stronger tier. Never down.
            </SectionHead>
            <Reveal delay={120}>
              <ul className="mt-8 grid gap-4 text-[14px] leading-6 text-ink-2">
                {[
                  ["Rules, not another LLM", "Routing uses step type, prompt size and retrieved documents, so it costs no quota."],
                  ["Capped and rate-limited", "A hard attempt cap and per-provider limits stop retry storms on free tiers."],
                  ["Every attempt is a row", "Provider, model, tier, reason, tokens and latency land in llm_calls."],
                ].map(([t, d]) => (
                  <li key={t} className="flex gap-3">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
                    <span><strong className="font-semibold text-ink">{t}.</strong> {d}</span>
                  </li>
                ))}
              </ul>
            </Reveal>
          </div>
          <Reveal delay={100}>
            <GatewayDemo />
            <p className="mt-3 font-mono text-[11px] text-muted">Illustrative sequence using the models configured in models.yaml.</p>
          </Reveal>
        </div>
      </section>

      {/* ───────── Workflows ───────── */}
      <section id="workflows" className="always-dark border-y border-line bg-ink text-paper">
        <div className="mx-auto w-full max-w-6xl px-5 py-24 sm:px-8 md:py-32">
          <Reveal className="max-w-2xl">
            <p className="eyebrow !text-paper/50">02 · Workflow engine</p>
            <h2 className="display mt-3 text-4xl leading-[1.05] sm:text-5xl">
              Runs that survive a <em className="text-signal">crashed worker</em>.
            </h2>
            <p className="mt-4 text-[15px] leading-7 text-paper/65">
              Workflows are versioned lists of steps. Each run and each step is a Postgres row, so state outlives
              any process. An arq worker executes them; a reaper recovers whatever got stuck.
            </p>
          </Reveal>

          <div className="mt-14 grid gap-4 md:grid-cols-3">
            {[
              ["llm", "Ask a model", "Routed and escalated by the gateway."],
              ["knowledge_search", "Search documents", "Workspace-scoped vector search."],
              ["mcp_tool", "Call a tool", "Schema-validated, timed out, logged."],
              ["agent", "Run an agent", "Bounded tool loop, five steps by default."],
              ["coordinator", "Plan and delegate", "A master agent splits a goal across specialists."],
              ["approval", "Ask a human", "Pauses the run until someone decides."],
            ].map(([ty, t, d], i) => (
              <Reveal key={ty} delay={i * 60}>
                <div className="group h-full rounded-2xl border border-paper/12 bg-paper/[0.04] p-5 transition-colors hover:border-signal/60 hover:bg-paper/[0.07]">
                  <p className="font-mono text-[11px] text-signal">{ty}</p>
                  <p className="mt-3 text-[17px] font-medium">{t}</p>
                  <p className="mt-1 text-[13.5px] leading-6 text-paper/55">{d}</p>
                </div>
              </Reveal>
            ))}
          </div>

          <Reveal delay={80}>
            <div className="mt-4 grid gap-px overflow-hidden rounded-2xl border border-paper/12 bg-paper/12 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["Idempotency keys", "A repeated trigger returns the same run."],
                ["Step leases", "Two workers never execute one step."],
                ["Resume", "Pick up at the first unfinished step."],
                ["Retries + timeouts", "Per step, with backoff."],
              ].map(([t, d]) => (
                <div key={t} className="bg-ink p-5">
                  <p className="font-mono text-[12px] text-paper">{t}</p>
                  <p className="mt-1.5 text-[13px] leading-5 text-paper/50">{d}</p>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ───────── Knowledge ───────── */}
      <section id="knowledge" className="mx-auto w-full max-w-6xl px-5 py-24 sm:px-8 md:py-32">
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          <Reveal className="order-2 lg:order-1">
            <div className={`${panel} overflow-hidden`}>
              <div className="border-b border-line px-5 py-3 font-mono text-[11px] text-muted">chat · Default workspace</div>
              <div className="grid gap-4 p-5 text-[14px] leading-6">
                <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-paper">
                  What is our refund window for annual plans?
                </div>
                <div className="max-w-[92%] rounded-2xl rounded-bl-md border border-line bg-paper px-4 py-3 text-ink-2">
                  Annual plans can be refunded within 30 days of purchase
                  <sup className="mx-0.5 rounded bg-signal-soft px-1 font-mono text-[10px] text-signal">1</sup>
                  ; after that, unused months are credited instead
                  <sup className="mx-0.5 rounded bg-signal-soft px-1 font-mono text-[10px] text-signal">2</sup>.
                </div>
                <div className="grid gap-2">
                  {[
                    ["1", "pricing.pdf", "“Annual subscriptions may be refunded in full within 30 days…”"],
                    ["2", "billing-faq.md", "“After 30 days, remaining months are issued as account credit…”"],
                  ].map(([n, f, q]) => (
                    <div key={n} className="rounded-lg border border-line bg-card px-3 py-2.5 text-[12px]">
                      <p className="font-mono text-[11px] text-muted"><span className="text-signal">[{n}]</span> {f}</p>
                      <p className="mt-1 text-ink-2">{q}</p>
                    </div>
                  ))}
                </div>
                <p className="font-mono text-[10.5px] text-muted">Sample conversation</p>
              </div>
            </div>
          </Reveal>
          <div className="order-1 lg:order-2">
            <SectionHead eyebrow="03 · Knowledge" title={<>Answers that show their <em>sources</em>.</>}>
              Upload .txt, .md or .pdf. Documents are parsed, chunked and embedded locally with a small ONNX model,
              straight into pgvector. Each answer is one model call with numbered passages, and the citations come back
              with it.
            </SectionHead>
            <Reveal delay={120}>
              <div className="mt-8 flex flex-wrap gap-2 font-mono text-[11.5px] text-ink-2">
                {["parse", "chunk ~1000 chars", "embed 384-dim", "HNSW cosine", "cited [n]"].map((s, i, a) => (
                  <span key={s} className="flex items-center gap-2">
                    <span className="rounded-full border border-line-strong bg-card px-3 py-1">{s}</span>
                    {i < a.length - 1 && <span className="text-signal">→</span>}
                  </span>
                ))}
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ───────── Approvals + tenancy ───────── */}
      <section className="mx-auto w-full max-w-6xl px-5 pb-24 sm:px-8 md:pb-32">
        <div className="grid gap-4 md:grid-cols-2">
          <Reveal>
            <div className={`${panel} h-full p-6 sm:p-8`}>
              <p className="eyebrow">04 · Human in the loop</p>
              <h3 className="display mt-3 text-3xl leading-tight">Risky tools wait for a person.</h3>
              <p className="mt-3 text-[14.5px] leading-7 text-muted">
                Flag a tool as requiring approval, or add an approval step. The run pauses as{" "}
                <code className="rounded bg-paper-2 px-1.5 py-0.5 font-mono text-[12px] text-ink">waiting_approval</code>.
                A member approves to resume or rejects to fail it.
              </p>
              <div className="mt-6 rounded-xl border border-wait/40 bg-wait-soft/60 p-4">
                <div className="flex items-center gap-2 font-mono text-[11.5px] text-wait">
                  <span className="pulse-dot h-2 w-2 rounded-full bg-wait text-wait" /> approval requested
                </div>
                <p className="mt-2 text-[13.5px] text-ink">Create issue in <span className="font-mono text-[12.5px]">acme/payments</span>?</p>
                <div className="mt-3 flex gap-2 text-[12.5px] font-medium">
                  <span className="rounded-md bg-ink px-3 py-1.5 text-paper">Approve</span>
                  <span className="rounded-md border border-line-strong px-3 py-1.5 text-ink-2">Reject</span>
                </div>
              </div>
            </div>
          </Reveal>
          <Reveal delay={100}>
            <div className={`${panel} h-full p-6 sm:p-8`}>
              <p className="eyebrow">05 · Multi-tenant by design</p>
              <h3 className="display mt-3 text-3xl leading-tight">Other tenants don’t exist. Literally.</h3>
              <p className="mt-3 text-[14.5px] leading-7 text-muted">
                Every workspace route resolves your membership first. A foreign resource returns 404, never 403, so
                its existence is never leaked. Roles run owner › admin › member › viewer.
              </p>
              <pre className="mt-6 overflow-x-auto rounded-xl bg-ink p-4 font-mono text-[12px] leading-6 text-paper/80">
{`GET /workspaces/`}<span className="text-paper/40">{`{theirs}`}</span>{`/runs
`}<span className="text-signal">404</span>{` Not Found   `}<span className="text-paper/40">{`# not 403`}</span>{`

GET /workspaces/`}<span className="text-paper/40">{`{mine}`}</span>{`/runs
`}<span className="text-ok">200</span>{` OK`}
              </pre>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ───────── Observability ───────── */}
      <section id="observe" className="border-y border-line bg-paper-2/60">
        <div className="mx-auto grid w-full max-w-6xl items-center gap-12 px-5 py-24 sm:px-8 md:py-32 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
          <SectionHead eyebrow="06 · Observability" title={<>Nothing happens <em>off the record</em>.</>}>
            A usage dashboard for calls, tokens, latency, fallback and failure rates, with the slowest steps one click
            from their run. An append-only audit log records sign-ins and every change. Rate limits and Prometheus
            metrics come standard.
          </SectionHead>
          <Reveal delay={100}>
            <div className={`${panel} p-5 sm:p-6`}>
              <div className="grid grid-cols-3 gap-3">
                {[["Calls", "12,408"], ["Tokens", "4.1M"], ["p95 latency", "2.1 s"]].map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-line bg-paper px-3.5 py-3">
                    <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{k}</p>
                    <p className="display mt-1 text-3xl leading-none">{v}</p>
                  </div>
                ))}
              </div>
              <div className="mt-6">
                <div className="mb-2 flex items-center justify-between font-mono text-[11px] text-muted">
                  <span>attempts per day</span>
                  <span className="flex items-center gap-1.5"><i className="inline-block h-2 w-2 rounded-sm bg-signal" /> failed</span>
                </div>
                <UsageBars />
              </div>
              <p className="mt-4 font-mono text-[10.5px] text-muted">Sample data</p>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ───────── Roadmap ───────── */}
      <section id="roadmap" className="mx-auto w-full max-w-6xl px-5 py-24 sm:px-8 md:py-32">
        <SectionHead eyebrow="07 · Roadmap" title={<>Honest about what’s <em>built</em>.</>}>
          This README is refreshed after every phase. Solid means it exists today; dashed means planned.
        </SectionHead>
        <ol className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {PHASES.map(([n, t, done], i) => (
            <Reveal key={n} delay={(i % 3) * 70}>
              <li
                className={`flex h-full gap-4 rounded-xl border p-4 ${
                  done ? "border-line-strong bg-card" : "border-dashed border-line-strong bg-transparent"
                }`}
              >
                <span className={`display text-3xl leading-none ${done ? "text-signal" : "text-line-strong"}`}>{n}</span>
                <div>
                  <p className={`text-[14px] leading-6 ${done ? "text-ink" : "text-muted"}`}>{t}</p>
                  <p className="mt-1 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted">{done ? "shipped" : "planned"}</p>
                </div>
              </li>
            </Reveal>
          ))}
        </ol>
      </section>

      {/* ───────── CTA ───────── */}
      <section className="mx-auto w-full max-w-6xl px-5 pb-24 sm:px-8">
        <Reveal>
          <div className="relative isolate overflow-hidden rounded-3xl bg-ink px-6 py-16 text-center text-paper sm:py-24">
            <svg className="absolute inset-0 -z-10 h-full w-full opacity-[0.18]" aria-hidden="true">
              <defs>
                <pattern id="cta-grid" width="32" height="32" patternUnits="userSpaceOnUse">
                  <path d="M32 0H0V32" fill="none" stroke="currentColor" strokeWidth="0.6" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#cta-grid)" />
            </svg>
            <svg className="absolute left-1/2 top-0 -z-10 h-full w-[120%] -translate-x-1/2 text-signal" viewBox="0 0 800 300" preserveAspectRatio="none" aria-hidden="true">
              <path className="flow-dash" d="M0 230 C 160 230, 220 90, 400 150 S 640 220, 800 70" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.7" />
            </svg>
            <h2 className="display mx-auto max-w-2xl text-4xl leading-[1.05] sm:text-6xl">
              Build the workflow. <em className="text-signal">Read the trace.</em>
            </h2>
            <p className="mx-auto mt-5 max-w-md text-[15px] leading-7 text-paper/65">
              Sign up and you get a personal organization and a default workspace, ready for your first document.
            </p>
            <div className="mt-9 flex flex-wrap justify-center gap-3">
              <Link href="/signup" className="inline-flex items-center rounded-lg bg-signal px-6 py-3 text-sm font-medium text-signal-ink transition-transform hover:-translate-y-0.5">
                Create a workspace
              </Link>
              <Link href="/login" className="inline-flex items-center rounded-lg border border-paper/25 px-6 py-3 text-sm font-medium text-paper transition-colors hover:bg-paper/10">
                Sign in
              </Link>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ───────── Footer ───────── */}
      <footer className="border-t border-line">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-start justify-between gap-8 px-5 py-10 sm:px-8 md:flex-row md:items-center">
          <div>
            <Logo size={24} />
            <p className="mt-3 max-w-xs text-[12.5px] leading-5 text-muted">
              An AI workbench for teams who want to see what their automations actually did.
            </p>
          </div>
          <DepsStatus />
        </div>
      </footer>
    </div>
  );
}
