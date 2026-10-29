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
| 0 | Foundations: monorepo, Docker Compose (Postgres/Mongo/Redis), config, lint, CI skeleton | ✅ |
| 1 | Data & auth: schema finalized, Alembic, JWT auth, orgs/workspaces/RBAC | ✅ |
| 2 | LLM layer: gateway + router + fallback (2a), agent runtime + coordinator/specialists + agents API (2b) | ✅ |
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

**Current phase:** 0, 1 and 2 complete; Phase 3 (Knowledge/RAG) next - needs its own approval gate. Phase 2 delivered: LLM gateway with automatic tier router, failure fallback and quality escalation; agents CRUD; single-agent runtime with a bounded tool loop; coordinator (master agent) with 4 built-in specialists; every model attempt logged to `llm_calls`.

### Phase 1 API surface (for later phases)
- `POST /auth/signup` (201 → token; creates user + personal org + "Default" workspace + owner membership), `POST /auth/login`, `GET /auth/me`.
- `GET/POST /organizations`, `GET/POST /organizations/{id}/members`, `GET/POST /organizations/{id}/workspaces`, `GET /workspaces/{id}`, `DELETE /workspaces/{id}` (admin+), `POST /workspaces/{id}/rename` (member+).
- Tenancy pattern: routes depend on `require_workspace` / `require_role(Role.X)` from `app/api/deps.py` and receive a `TenantContext` (user, workspace, org, membership, role). Non-members get 404 (existence never leaks), insufficient role gets 403.
- Role rules: owner > admin > member > viewer (org membership decides workspace access). Adding members: admin+ may only grant roles strictly below their own; only owners can grant admin; nobody can grant owner via API.

## Open questions (unresolved)
- Python package manager (uv recommended) and Python version. *(uv +3.12 used for backend scaffold — confirm OK)*
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
| 2026-10-27 | Node 24 LTS + npm for frontend | Installed on machine (no pnpm/yarn); simple for free PaaS deploy |
| 2026-10-27 | Tailwind CSS for frontend styling | User choice; native create-next-app support, fast iteration |
| 2026-10-28 | bcrypt directly (not passlib[bcrypt]) | passlib is unmaintained and breaks with bcrypt>=4.1 |
| 2026-10-28 | JWT in frontend localStorage (not httpOnly cookie) | Simplest for a portfolio project; revisit before untrusted deployments |
| 2026-10-28 | Tests run real Alembic migration against docker Postgres `cogniflow_test` (not SQLite) | Validates pgvector extension + migration itself; sqlite would hide Postgres-specific breakage |
| 2026-10-28 | Signup = user + personal org + "Default" workspace + owner membership | Users can use the app immediately; POST /organizations still exists for more orgs |
| 2026-10-28 | Non-members get 404 (not 403) on org/workspace resources | Don't leak existence of other tenants' resources |
| 2026-10-28 | Member grants: strictly below own rank; only owners grant admin; nobody grants owner via API | Prevents privilege escalation by admins |
| 2026-10-28 | JWT_SECRET must be >= 32 bytes (HS256, RFC 7518) | pyjwt warns on short keys; dev default padded accordingly |

## Repo layout
Current: `OVERVIEW`, `agentcontext.md`, `docker-compose.yml`, root `.env.example`/`.gitignore`, `backend/` (uv project: `pyproject.toml`, `alembic.ini`, `alembic/{env.py,script.py.mako,versions/0001_initial_auth.py}`, `app/{config,main}.py`, `app/core/security.py`, `app/models/{base,enums,user,organization,workspace}.py`, `app/schemas/{auth,org}.py`, `app/api/{health,auth,organizations,workspaces,deps}.py`, `app/db/{postgres,mongo,redis}.py`, `tests/{conftest,test_health,test_auth,test_tenancy}.py`), `frontend/` (Next.js 16.4.3 + TS + Tailwind 4, App Router, `src/` dir: `app/{layout,page,deps-status,login,signup,dashboard}`, `lib/{api,auth}.ts`, `types/index.ts`, `.env.example`).
Also: `db-schema.mmd` (Phase 1 blueprint), `.github/workflows/ci.yml` (backend job now has a pgvector Postgres service container).

### Commands / setup notes for other agents
- Backend dev server: `cd backend && uv run uvicorn app.main:app --reload --port 8001` (8000 is taken by another app on this machine).
- Migrations: `cd backend && uv run alembic upgrade head` (needs `docker compose up -d`). Env.py adds backend/ to sys.path itself.
- Tests: `cd backend && uv run pytest` — requires docker Postgres up; conftest creates/migrates `cogniflow_test` and truncates tables per test. Never point tests at the dev `cogniflow` DB.
- New env vars (both `.env.example` and `backend/.env` updated): `JWT_SECRET` (>= 32 bytes for HS256), `JWT_EXPIRE_MINUTES` (default 1440).
- New deps: `pyjwt`, `bcrypt`, `email-validator` (backend); ruff config now sets `extend-immutable-calls` for FastAPI's `Depends()` pattern.
- Frontend: `cd frontend && npm run dev` (http://localhost:3000). Token lives in localStorage (`cogniflow_token`/`cogniflow_user`); `lib/api.ts` attaches the Bearer header and clears the token on 401.

## Session log
Append newest at the bottom. Format: `date · agent · files changed · what/why · next step`.

- 2026-10-27 · Claude Code · Reviewed OVERVIEW and schema, settled stack and 12-phase roadmap, created this file. Next: user answers open questions → Phase 0 breakdown for approval.
- 2026-10-27 · Claude Code · Created empty directory skeleton (`backend/{app,alembic/versions,tests}/`, `frontend/`, `.gitkeep`s). Next: answer open questions → Phase 0 file-by-file breakdown for approval.
- 2026-10-27 · Claude Code · agentcontext.md · Added mandatory rule that every agent logs all repo changes/decisions here (session log, status table, decisions, open questions, layout, setup notes) and reads recent log entries before starting. Next: user answers open questions → Phase 0 breakdown for approval.
- 2026-10-27 · Claude Code · created `docker-compose.yml` (pgvector/pg16, mongo:7, redis:7 with healthchecks), `.env.example`, `.gitignore`, `backend/` uv project (Python 3.12 pinned; deps: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pgvector, motor, redis, pydantic-settings; dev: pytest, pytest-asyncio, httpx, ruff), `backend/app/{config,main}.py`, `app/db/{postgres,mongo,redis}.py`, `app/api/health.py` (`/health`, `/health/deps`), `tests/test_health.py`, ruff+pytest config. Used defaults for open questions: uv, Python 3.12. `ruff` and `pytest` pass. NOT verified: `/health/deps` against real DBs (Docker daemon was not running). Noticed `db-schema.mmd` missing from disk. Next: start Docker, run `docker compose up -d`, `cd backend && uv run uvicorn app.main:app --reload`, check `/health/deps`; then Phase 1 breakdown for approval.
- 2026-10-27 · OpenCode (MiMo) · frontend scaffold for Phase 0 (user-approved breakdown): `create-next-app` (Next.js 16.4.3, TS, ESLint, Tailwind 4, App Router, `src/`, npm, no nested git), `src/app/layout.tsx` (metadata → "AI Workbench"), `src/app/page.tsx` (landing shell), `frontend/.env.example` (`NEXT_PUBLIC_API_URL`), `src/lib/api.ts` (typed fetch client stub), `src/types/index.ts` (placeholder User/Workspace/Workflow/WorkflowRun), `frontend/.gitignore` (`!.env.example` exception), this file (layout/status/decisions/open-questions). Read bundled Next 16 docs per `AGENTS.md` before writing code. `npm run lint` + `npm run build` pass. Open question resolved: Node 24 + npm. Next: CI skeleton + Docker verification to finish Phase 0, then Phase 1 breakdown for approval.
- 2026-10-27 · Claude Code · agentcontext.md · Verified: `docker compose up -d` healthy; backend `/health` and `/health/deps` return ok for postgres/mongo/redis. Port 8000 is used by the user's other project (cold-call-assistant), so run Cogniflow with `uv run uvicorn app.main:app --reload --port 8001`. Mistake: a `pkill -f "uvicorn app.main"` I ran likely stopped that other app; do not use broad pkill, kill only your own PID. Next: frontend scaffold (awaiting npm/pnpm + Tailwind confirmation) and Phase 1 breakdown.
- 2026-10-27 · Claude Code · frontend/.env.example, frontend/.env.local · Changed NEXT_PUBLIC_API_URL to http://localhost:8001 (8000 is the user's other app); created git-ignored .env.local. A duplicate nested `frontend/frontend/` (from running create-next-app inside frontend/) had already been removed. Run: backend `uv run uvicorn app.main:app --reload --port 8001`, frontend `cd frontend && npm run dev` (http://localhost:3000). Next: verify landing page reaches API; Phase 1 breakdown.
- 2026-10-28 · Claude Code · `backend/app/{config,main}.py` (CORS middleware, `CORS_ORIGINS` setting defaulting to `http://localhost:3000`), `backend/tests/test_health.py` (CORS test), `.github/workflows/ci.yml` (backend: uv sync, ruff, pytest; frontend: npm ci, lint, build), `frontend/src/app/{deps-status.tsx,page.tsx}` (landing page shows `/health/deps`), `db-schema.mmd` recreated from OVERVIEW/agentcontext incl. CONVERSATIONS, `WORKFLOW_RUNS.conversation_id`/`idempotency_key`/`queue_job_id`, `STEP_RUNS.trace_ref`/`idempotency_key`, `DOCUMENTS.content_hash`. Verified: ruff+pytest (2 pass), frontend lint+build, both apps run, curl shows CORS header and all deps ok. CI not yet run on GitHub. Phase 0 done. Next: Phase 1 breakdown (finalize schema, Alembic, JWT auth, orgs/RBAC).
- 2026-10-28 · OpenCode (MiMo) · Phase 1 approved file-by-file breakdown (user chose all recommended options): bcrypt directly (not passlib), JWT in frontend localStorage (not httpOnly cookie), tests run against real Postgres `cogniflow_test` DB with the actual Alembic migration (not SQLite), signup creates user + personal org + "Default" workspace + owner membership. agentcontext.md updated (Phase 1 → 🟡).
- 2026-10-28 · OpenCode (MiMo) · **Phase 1 implemented and verified.** Backend: `app/models/{base,enums,user,organization,workspace,__init__}.py` (User/Organization/Membership/Workspace, UUID pks, Role StrEnum with rank()); `app/core/security.py` (bcrypt hash/verify, PyJWT create/decode with sub=uuid, exp); `app/config.py` + root/.env `JWT_SECRET` (>=32 bytes, HS256 warning), `JWT_EXPIRE_MINUTES`; `alembic.ini` + `alembic/env.py` (async, adds backend/ to sys.path) + `alembic/versions/0001_initial_auth.py` (CREATE EXTENSION vector + users/organizations/memberships/workspaces w/ FKs, unique email/slug/user+org, indexes) — applied to dev DB; `app/schemas/{auth,org}.py`; `app/api/deps.py` (`get_current_user` via HTTPBearer, `require_workspace`→TenantContext, `require_role(min)` factory; non-members → 404 to avoid leaking existence); `app/api/auth.py` (signup 201/login/me), `app/api/organizations.py` (list/create orgs, members list/add w/ "grant strictly below own rank" rule, workspaces list/create), `app/api/workspaces.py` (get/delete-admin/rename-member — the tenant pattern for later phases); `app/main.py` wires routers; pyproject adds pyjwt/bcrypt/email-validator + ruff `extend-immutable-calls` for Depends(). Frontend: `types/index.ts` (real User/Org/Workspace/Role/TokenResponse), `lib/auth.ts` (localStorage token+user helpers), `lib/api.ts` (auto Bearer header, clear-on-401, auth API fns), `app/login/page.tsx` + `app/signup/page.tsx` (client forms → store token → /dashboard), `app/dashboard/page.tsx` (fetch me + orgs + workspaces, logout), landing page nav links to login/signup (read bundled Next 16 docs first per AGENTS.md). Tests: `tests/conftest.py` (creates+migrates `cogniflow_test` via real alembic upgrade, truncates per test, engine.dispose() to avoid cross-loop pooling), `test_auth.py` (10 tests), `test_tenancy.py` (11 tests incl. cross-tenant 404s, viewer/member/admin/owner role gates, privilege-escalation prevention). CI: added pgvector Postgres service to backend job. Verified: ruff clean, 21/21 pytest pass, frontend lint+build pass, manual curl smoke test of signup→login→me→orgs→workspace get/rename + cross-user 404. Fixed during work: SQLAlchemy text() for TRUNCATE, admin-could-grant-admin bug (rule tightened to >=), short JWT key warning, lint B008/E501/I001. Not committed (per rules). Next: Phase 2 (LLM layer) breakdown for approval.
- 2026-10-29 · Claude Code · backend/.env (git-ignored), .env.example · Added OPENROUTER_API_KEY and GROQ_API_KEY to backend/.env (values supplied by user, never commit) and empty placeholders to .env.example. Not yet read by app Settings (added in Phase 2). Next: user decides LLM-layer architecture, then Phase 2 breakdown for approval.
- 2026-10-29 · Claude Code · **Phase 2a implemented (user-approved breakdown: build 2a, stop for review, then 2b).** Decisions: router = automatic rules (step_type, token estimate, #documents) + quality escalation, no classifier; optional per-agent tier/model pin; free models only; MVP gets a coordinator + specialist agents (2b). New: `backend/app/llm/{types,errors,base,registry,router,ratelimit,gateway,deps,recording}.py`, `llm/providers/{openai_compat,groq,openrouter}.py`, `llm/models.yaml` (tiers small/medium/large + last_resort; Groq primary, OpenRouter free fallbacks), `app/models/{agent,llm_call}.py`, migration `0002_agents_llm_calls` (applied to dev DB), `app/api/llm.py` (`POST /workspaces/{id}/llm/chat`, member+; records every attempt to `llm_calls`), config (`groq_api_key`, `openrouter_api_key`, rpm limits, timeout, max attempts), `main.py` (router + gateway shutdown), `pyproject.toml` (httpx moved to runtime deps, pyyaml added), tests `fakes.py`, `test_llm_gateway.py`, `test_llm_api.py`, `test_llm_live.py` (opt-in: `RUN_LIVE_LLM=1`). Gateway behaviour: 429 -> next model (no retry); timeout/5xx -> 1 retry w/ backoff then next model; 4xx/bad model -> skip; invalid/empty output -> skip rest of tier and escalate up (never down); then last_resort; hard cap `llm_max_attempts`=8; Redis fixed-window per-provider rpm limiter (fails open). Providers without a key are skipped. Verified live 2026-10-29: all 3 Groq models OK; OpenRouter gemma/lfm/xing are valid but often 429; `thinkingmachines/inkling:free` is 403 (agentic-harness only) so replaced by `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`. 42 tests pass (1 live skipped), ruff clean. Agents CRUD API is NOT built yet (only the table/model) - it is part of 2b. Notes: Docker Desktop had stopped; restart with `open -a Docker` then `docker compose up -d`. Test gotcha: asyncpg/httpx objects are bound to one event loop - use ONE asyncio.run per test body and a separate engine in test helpers. Next: user reviews 2a, then 2b (agent runtime, specialists, coordinator, agents CRUD, run endpoints).
- 2026-10-29 · Claude Code · **Phase 2b implemented and verified.** New: `backend/app/agents/{config,tools,runtime,specialists,coordinator,deps}.py`, `backend/app/api/agents.py` (routers registered in `main.py`). Changed: `app/llm/{types,gateway,recording}.py` (every `Attempt` now carries `route_reason` and `agent_id`; gateway stamps the reason on all attempts incl. failures; recorder uses them). API: `GET/POST /workspaces/{id}/agents` (list = any member incl. viewer; create = admin+), `GET/PATCH/DELETE /workspaces/{id}/agents/{agent_id}` (patch/delete admin+; agent ids are scoped to the workspace, foreign ids -> 404), `POST /workspaces/{id}/agents/{agent_id}/run` (member+), `POST /workspaces/{id}/coordinator/run` (member+). Agent fields: name (unique per workspace -> 409), role (research|analysis|writing|review|custom), system_prompt, optional `tier_pin` (small|medium|large) and `model_pin` ("provider:model") overriding the router, params (JSON, passed to the model e.g. temperature/max_tokens). Runtime tool protocol: model replies with ONLY `{"tool","arguments"}` JSON to call a tool, anything else is the final answer; tool results are fed back as untrusted data; unknown tool / missing args / exception / timeout become tool_error steps (exception details are NOT leaked to the model); tools with `requires_approval` are refused until phase 6; loop capped at `max_steps`=5 (status `step_limit`). No tools are registered yet (`app/agents/deps.py:get_tools` returns an empty registry; RAG in phase 3 and MCP in phase 4 should register tools there). Coordinator: LARGE-tier planner returns JSON steps (<=5, roles must be in SPECIALISTS; invalid plan fails the gateway validator so it escalates to a stronger model), runs each step via the specialist for that role (a workspace Agent with the same role overrides the built-in; first by created_at), adds a writer synthesis step unless the last step is writing; a failing step returns status `failed` with partial results (HTTP 200); planning failure -> 502. Planner prompt asks for the fewest steps (free-tier quota). Verified live: coordinator ran end to end on Groq (gpt-oss-120b planner/analysis, qwen3.8-27b writing) with all attempts successful. 66 tests pass (+1 opt-in live skipped), ruff clean. No new migration (tables from 0002 reused). Frontend for agents NOT built (planned for phase 7). Known gaps: coordinator steps run sequentially; llm token usage is logged but cost is always 0 (free models); no streaming. Next: Phase 3 (Knowledge/RAG) breakdown for approval - open questions: file storage (local volume vs R2), embedding model (local sentence-transformers recommended), chunking strategy, supported file types.
