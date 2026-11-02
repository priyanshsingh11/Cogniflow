import asyncio
import datetime
import uuid

from sqlalchemy import func, or_, select, update

from app.config import settings
from app.db.postgres import SessionLocal
from app.models.workflow import Approval, StepRun, WorkflowRun, WorkflowStep, WorkflowVersion
from app.workflows.compiler import WorkflowState, compile_workflow_graph
from app.workflows.steps import STEP_HANDLERS, StepExecutionContext, StepResult


class StepLeaseError(Exception):
    """Raised when a step run cannot be leased because another worker holds it."""


class StepExecutionError(Exception):
    """Raised when a step run permanently fails all retry attempts."""


async def execute_run(
    run_id: uuid.UUID,
    *,
    resume: bool = False,
    worker_id: str | None = None,
) -> WorkflowRun:
    """Execute a workflow run durably with LangGraph and Postgres."""
    worker_uuid = worker_id or str(uuid.uuid4())

    async with SessionLocal() as session:
        run = await session.get(WorkflowRun, run_id)
        if run is None:
            raise ValueError(f"WorkflowRun {run_id} not found")

        # Idempotency check: if already completed and not resuming
        if run.status in ("succeeded", "failed", "cancelled") and not resume:
            return run
        if run.status == "waiting_approval" and not resume:
            return run

        # Set status to running
        run.status = "running"
        if run.started_at is None:
            run.started_at = datetime.datetime.now(datetime.UTC)
        await session.commit()

        # Load version and steps
        version = await session.get(WorkflowVersion, run.workflow_version_id)
        if version is None:
            raise ValueError(f"WorkflowVersion {run.workflow_version_id} not found")

        stmt = (
            select(WorkflowStep)
            .where(WorkflowStep.workflow_version_id == version.id)
            .order_by(WorkflowStep.position)
        )
        steps = list((await session.execute(stmt)).scalars().all())
        if not steps:
            run.status = "succeeded"
            run.finished_at = datetime.datetime.now(datetime.UTC)
            run.output = {}
            await session.commit()
            return run

        # Load existing step_runs for resume capability
        sr_stmt = select(StepRun).where(StepRun.workflow_run_id == run.id)
        existing_step_runs = list((await session.execute(sr_stmt)).scalars().all())

        initial_state: WorkflowState = {
            "run_id": str(run.id),
            "workspace_id": str(run.workspace_id),
            "input": run.input or {},
            "steps": {},
            "current_step": "",
            "next_step": None,
            "status": "running",
            "error": None,
            "waiting_approval_step": None,
            "waiting_approval_details": None,
        }

        # Seed steps output from previously succeeded step runs
        for sr in existing_step_runs:
            if sr.status == "succeeded" and sr.output is not None:
                initial_state["steps"][sr.step_name] = sr.output

    # Step callback invoked by LangGraph nodes
    async def step_callback(step: WorkflowStep, state: WorkflowState) -> WorkflowState:
        # 1. Skip if already succeeded
        if step.name in state["steps"]:
            return state

        async with SessionLocal() as step_session:
            # 2. Find or create StepRun
            sr_query = (
                select(StepRun)
                .where(
                    StepRun.workflow_run_id == run_id,
                    StepRun.step_name == step.name,
                )
                .order_by(StepRun.attempt.desc())
                .limit(1)
            )
            sr_row = (await step_session.execute(sr_query)).scalar_one_or_none()

            now = datetime.datetime.now(datetime.UTC)
            if sr_row is None:
                attempt = 1
                idempotency_key = f"{run_id}:{step.name}:{attempt}"
                step_run = StepRun(
                    workflow_run_id=run_id,
                    workflow_step_id=step.id,
                    step_name=step.name,
                    attempt=attempt,
                    idempotency_key=idempotency_key,
                    status="pending",
                    input=state["steps"].get(step.name) or state["input"],
                )
                step_session.add(step_run)
                await step_session.flush()
            else:
                step_run = sr_row

            # 3. Acquire step lease
            expires_at = now + datetime.timedelta(seconds=settings.step_lease_duration_seconds)
            lease_stmt = (
                update(StepRun)
                .where(
                    StepRun.id == step_run.id,
                    or_(
                        StepRun.lease_expires_at.is_(None),
                        StepRun.lease_expires_at < now,
                        StepRun.lease_worker_id == worker_uuid,
                        StepRun.status == "pending",
                        StepRun.status == "waiting_approval",
                    ),
                )
                .values(
                    lease_worker_id=worker_uuid,
                    lease_expires_at=expires_at,
                    status="running",
                    started_at=func.coalesce(StepRun.started_at, now),
                )
            )
            res = await step_session.execute(lease_stmt)
            if res.rowcount == 0:
                raise StepLeaseError(f"Step '{step.name}' is currently leased by another worker")
            await step_session.commit()

            # 4. Execute handler with retries and timeout
            handler = STEP_HANDLERS.get(step.type)
            if handler is None:
                raise ValueError(f"Unknown step type: {step.type}")

            max_retries = int(step.config.get("max_retries", 0))
            timeout_sec = float(
                step.config.get("timeout_seconds", settings.step_default_timeout_seconds)
            )
            backoff_sec = float(step.config.get("retry_backoff_seconds", 1.0))

            step_result: StepResult | None = None
            last_error: Exception | None = None

            for current_attempt in range(max_retries + 1):
                try:
                    exec_ctx = StepExecutionContext(
                        session=step_session,
                        workspace_id=uuid.UUID(state["workspace_id"]),
                        run_id=run_id,
                        step_run_id=step_run.id,
                        step_name=step.name,
                        step_config=step.config,
                        context={"input": state["input"], "steps": state["steps"]},
                        agent_id=step.agent_id,
                    )
                    step_result = await asyncio.wait_for(
                        handler(exec_ctx),
                        timeout=timeout_sec,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    if current_attempt < max_retries:
                        await asyncio.sleep(backoff_sec * (current_attempt + 1))
                        # Refresh attempt on step_run
                        step_run.attempt += 1
                        await step_session.commit()
                        continue
                    else:
                        break

            # Handle step failure
            if step_result is None:
                err_msg = str(last_error) if last_error else "Step timed out or failed"
                step_run.status = "failed"
                step_run.error = err_msg
                step_run.finished_at = datetime.datetime.now(datetime.UTC)
                step_run.lease_worker_id = None
                step_run.lease_expires_at = None

                db_run = await step_session.get(WorkflowRun, run_id)
                if db_run:
                    db_run.status = "failed"
                    db_run.error = f"Step '{step.name}' failed: {err_msg}"
                    db_run.finished_at = datetime.datetime.now(datetime.UTC)

                await step_session.commit()
                state["status"] = "failed"
                state["error"] = err_msg
                return state

            # 5. Handle approval pause (Phase 6)
            if step_result.status == "waiting_approval":
                step_run.status = "waiting_approval"
                step_run.lease_worker_id = None
                step_run.lease_expires_at = None

                db_run = await step_session.get(WorkflowRun, run_id)
                if db_run:
                    db_run.status = "waiting_approval"

                appr_details = step_result.approval_details or {}
                approval = Approval(
                    workspace_id=uuid.UUID(state["workspace_id"]),
                    workflow_run_id=run_id,
                    step_run_id=step_run.id,
                    status="pending",
                    description=appr_details.get("description"),
                    details=appr_details.get("details") or appr_details,
                )
                step_session.add(approval)
                await step_session.commit()

                state["status"] = "waiting_approval"
                state["waiting_approval_step"] = step.name
                state["waiting_approval_details"] = appr_details
                return state

            # 6. Handle step success
            step_run.status = "succeeded"
            step_run.output = step_result.output
            step_run.finished_at = datetime.datetime.now(datetime.UTC)
            step_run.lease_worker_id = None
            step_run.lease_expires_at = None
            await step_session.commit()

            state["steps"][step.name] = step_result.output
            state["current_step"] = step.name
            state["next_step"] = step_result.next_step
            return state

    # Compile and execute graph
    graph = compile_workflow_graph(steps, step_callback)
    final_state = await graph.ainvoke(initial_state)

    # 7. Finalize WorkflowRun
    async with SessionLocal() as final_session:
        final_run = await final_session.get(WorkflowRun, run_id)
        if final_run is not None:
            if final_state.get("status") == "waiting_approval":
                final_run.status = "waiting_approval"
            elif final_state.get("status") == "failed":
                final_run.status = "failed"
                final_run.error = final_state.get("error")
                final_run.finished_at = datetime.datetime.now(datetime.UTC)
            elif final_run.status not in ("cancelled", "failed", "waiting_approval"):
                final_run.status = "succeeded"
                final_run.output = final_state.get("steps")
                final_run.finished_at = datetime.datetime.now(datetime.UTC)
            await final_session.commit()
            await final_session.refresh(final_run)
            return final_run

    async with SessionLocal() as check_session:
        return await check_session.get(WorkflowRun, run_id)  # type: ignore[return-value]
