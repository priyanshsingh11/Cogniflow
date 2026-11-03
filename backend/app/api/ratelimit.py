"""Route-level rate-limit dependencies (phase 8).

Each is a plain FastAPI dependency, so ordering in a handler signature puts
the limit before the work it protects. Limits are read from `settings` at
call time (tests shrink them via monkeypatch).
"""

from fastapi import Depends, Request

from app.api.deps import TenantContext, require_member, require_workspace
from app.config import settings
from app.core.ratelimit import client_ip, enforce

LOGIN_WINDOW_SECONDS = 300
SIGNUP_WINDOW_SECONDS = 3600
USER_WINDOW_SECONDS = 60
WORKSPACE_WINDOW_SECONDS = 60


async def _body_email(request: Request) -> str | None:
    """Best-effort email from the login body (invalid JSON -> None)."""
    try:
        body = await request.json()
    except Exception:
        return None
    email = body.get("email") if isinstance(body, dict) else None
    return str(email).strip().lower() or None


async def limit_login(request: Request) -> None:
    """Per IP and per email: slows brute-force password guessing."""
    await enforce(
        "login_ip",
        f"ip:{client_ip(request)}",
        settings.rl_login_ip_per_5min,
        LOGIN_WINDOW_SECONDS,
    )
    email = await _body_email(request)
    if email:
        await enforce(
            "login_email",
            f"email:{email}",
            settings.rl_login_email_per_5min,
            LOGIN_WINDOW_SECONDS,
        )


async def limit_signup(request: Request) -> None:
    await enforce(
        "signup_ip",
        f"ip:{client_ip(request)}",
        settings.rl_signup_ip_per_hour,
        SIGNUP_WINDOW_SECONDS,
    )


def per_user_limit(bucket: str, setting_name: str):
    """Limit every call a member makes on an LLM-costing endpoint."""

    async def dependency(ctx: TenantContext = Depends(require_member)) -> None:
        await enforce(
            bucket,
            f"user:{ctx.user.id}",
            getattr(settings, setting_name),
            USER_WINDOW_SECONDS,
        )

    return dependency


def per_workspace_limit(bucket: str, setting_name: str):
    """Limit a shared workspace-scoped action (e.g. triggering runs)."""

    async def dependency(ctx: TenantContext = Depends(require_workspace)) -> None:
        await enforce(
            bucket,
            f"ws:{ctx.workspace.id}",
            getattr(settings, setting_name),
            WORKSPACE_WINDOW_SECONDS,
        )

    return dependency


# Prebuilt singletons (routers already use this pattern for require_*).
limit_llm_user = per_user_limit("llm", "rl_llm_user_per_min")
limit_tool_user = per_user_limit("tool", "rl_tool_user_per_min")
limit_runs_workspace = per_workspace_limit("runs", "rl_runs_ws_per_min")
