# Cogniflow (AI Workbench) – Agent Context

Shared context for any coding agent (Claude Code, Cursor, Copilot, etc.) working on this repo. **Read this first. Update it at the end of every work session.**

## Working rules
1. **Phase-gated:** implement one phase at a time. Do not start a phase without explicit user approval of its file-by-file breakdown.
2. **Plan before code:** propose changes, get approval, then implement.
3. **Do not commit or push** unless the user asks.
4. **Every change must be recorded here (mandatory).** Whenever an agent changes anything in the repo (code, config, schema, docs, dependencies, infra) or makes a decision, it must update this file in the same session, before finishing:
   - Add a *Session log* entry: date, agent name, files created/modified/deleted, what and why, and what's next.
   - Update the *Roadmap and status* table and *Current phase* if progress changed.
   - Update *Decisions log*, *Open questions*, *Tech stack*, *Data ownership rules* and *Repo layout* if they are affected.
   - Note any new commands, env vars, or setup steps another agent needs to know.
   - If you changed nothing, don't log anything. If a change is not recorded here, treat it as incomplete.
5. Before starting work, read the latest *Session log* entries so you don't redo or contradict earlier work.
6. Match existing code style; don't add features outside the current phase.

## Project summary
Multi-tenant platform to build, run and monitor AI workflows: document RAG with citations, configurable agents, MCP tool integration, human approval steps, execution history/observability, and evaluation. Portfolio project, 2–3 months part-time. Full description: [OVERVIEW](OVERVIEW). Data model: [db-schema.mmd](db-schema.mmd). Approved roadmap: `~/.claude/plans/so-now-start-from-enchanted-rabin.md`.

## Tech stack (decided)
| Area | Choice |
|---|---|
| Backend | FastAPI (Python), SQLAlchemy async, Alembic |
| Frontend | Next.js + TypeScript; form-based step list first, React Flow canvas later |
| System of record | PostgreSQL + pgvector (embeddings live here, no separate vector DB) |
| Flexible data | MongoDB: conversation messages, agent memory, step traces |
| Queue / cache | Redis + arq everywhere, behind a queue interface (no SQS) |
| Orchestration | LangGraph; Postgres `workflow_runs`/`step_runs` remain the authoritative record |
| LLMs | Provider abstraction; free providers (Groq, OpenRouter) |
| Auth | Self-built JWT (email + password), org/workspace RBAC |
| MCP | GitHub MCP + filesystem/fetch reference servers (free only) |
| Local dev | Docker Compose (Postgres+pgvector, MongoDB, Redis) |
| Deploy | Free PaaS (Render/Fly/Railway) + Neon (Postgres) + Atlas (Mongo) + hosted Redis |

## Data ownership rules
- **Postgres** = source of truth: users, orgs, memberships, workspaces, documents/chunks/vectors, agents, MCP servers/tools, workflows/versions/steps, runs, step runs, tool calls, approvals, LLM call summaries, audit logs, evals.
- **MongoDB** = flexible AI data only: `messages`, `agent_memory`, `step_traces`. Documents reference Postgres UUIDs (`workspace_id`, `conversation_id`, `step_run_id`). Never the reverse.
- **Redis** = queue, locks, caching, rate limits. Anything in it must be rebuildable from Postgres.
- Check permissions in Postgres **before** touching Mongo; every Mongo query is filtered by `workspace_id`.
- Cross-DB writes: Postgres row first (`pending`) → Mongo write → flip status. A reaper job retries stuck rows. Use idempotency keys; no cross-DB joins.
- Planned schema additions vs current `db-schema.mmd`: `CONVERSATIONS` table (with `mongo_conversation_id`), `WORKFLOW_RUNS.conversation_id`, `STEP_RUNS.trace_ref` and a dedupe/idempotency key for queued jobs.

## Roadmap and status
Legend: ⬜ not started · 🟡 in progress · ✅ done

| # | Phase | Status |
|---|---|---|
| 0 | Foundations: monorepo, Docker Compose (Postgres/Mongo/Redis), config, lint, CI skeleton | ⬜ |
| 1 | Data & auth: schema finalized, Alembic, JWT auth, orgs/workspaces/RBAC | ⬜ |
| 2 | LLM layer: provider interface, per-agent model config, usage/cost logging | ⬜ |
| 3 | Knowledge/RAG: upload, chunk, embed, pgvector search, cited answers, chat in Mongo | ⬜ |
| 4 | MCP layer: register servers, discover/validate/invoke tools, TOOL_CALLS logging | ⬜ |
| 5 | Workflow engine: workflow API, LangGraph executor on arq, retries/timeouts/idempotency/resume | ⬜ |
| 6 | Human approval: pause/resume runs, approvals API | ⬜ |
| 7 | Frontend MVP: auth, upload+chat, step-list workflow editor, run history, approval inbox | ⬜ |
| 8 | Observability & safety: audit logs, rate limits, usage dashboard | ⬜ |
| 9 | Evaluation: datasets, cases, runs, results | ⬜ |
| 10 | Visual builder (React Flow), multi-agent, schedule/webhook triggers | ⬜ |
| 11 | Deploy & polish: PaaS deploy, CI/CD, tests, README, demo | ⬜ |

MVP = phases 0–7 (matches OVERVIEW "Initial Scope").

**Current phase:** none started. Awaiting answers to the open questions below, then a Phase 0 breakdown for approval.

## Open questions (unresolved)
- Python package manager (uv recommended) and Python version.
- Node version and package manager (npm/pnpm/yarn).
- File storage without S3: local volume in dev + Cloudflare R2 in prod?
- Embedding model: local sentence-transformers vs OpenRouter.
- LangGraph checkpointer in Postgres with `step_runs` as user-facing record (recommended) vs `step_runs` only.
- Encryption approach for MCP credentials (`MCP_SERVERS.secret_ref`).

## Decisions log
| Date | Decision | Why |
|---|---|---|
| 2026-10-27 | Hybrid Postgres + MongoDB; Postgres authoritative | Relational integrity for workflows/runs; Mongo only where flexible docs help |
| 2026-10-27 | pgvector only, no separate vector DB | One fewer service; simple tenant filtering |
| 2026-10-27 | Redis + arq everywhere, no SQS | Deploying on free PaaS, not AWS |
| 2026-10-27 | LangGraph for orchestration | User choice; Postgres tables stay the durable record |
| 2026-10-27 | Form-based workflow editor first | Get engine working before React Flow canvas |
| 2026-10-27 | Phase-by-phase with approval gates | User wants control over each implementation step |

## Repo layout
Current: `OVERVIEW`, `db-schema.mmd`, `agentcontext.md`, empty skeleton dirs `backend/{app,alembic/versions,tests}/` and `frontend/` (`.gitkeep` only, no code).
Planned (Phase 0): fill in `backend/` (pyproject, app package, Alembic), `frontend/` (Next.js), `docker-compose.yml`, `.env.example`, lint/CI skeleton. Note: `db-schema.mmd` is referenced but does not exist yet.

## Session log
Append newest at the bottom. Format: `date · agent · files changed · what/why · next step`.

- 2026-10-27 · Claude Code · Reviewed OVERVIEW and schema, settled stack and 12-phase roadmap, created this file. Next: user answers open questions → Phase 0 breakdown for approval.
- 2026-10-27 · Claude Code · Created empty directory skeleton (`backend/{app,alembic/versions,tests}/`, `frontend/`, `.gitkeep`s). Next: answer open questions → Phase 0 file-by-file breakdown for approval.
- 2026-10-27 · Claude Code · agentcontext.md · Added mandatory rule that every agent logs all repo changes/decisions here (session log, status table, decisions, open questions, layout, setup notes) and reads recent log entries before starting. Next: user answers open questions → Phase 0 breakdown for approval.
