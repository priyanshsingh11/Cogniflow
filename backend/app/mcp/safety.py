"""MCP safety rails (phase 8 extras): command allowlist + credential crypto.

- ``require_command_allowed`` gates which executables a stdio server may
  launch, at registration *and* at spawn (defence in depth for rows written
  before the rule existed or straight from the DB).
- ``encrypt_credentials`` / ``decrypt_credentials`` keep per-server secrets
  (HTTP headers such as ``Authorization``, stdio env such as ``GITHUB_TOKEN``)
  encrypted at rest. The key is derived from ``jwt_secret``, so rotating the
  secret invalidates stored credentials (they must be re-entered).
"""

import base64
import hashlib
import json
import os
import re
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class CommandNotAllowedError(Exception):
    """The stdio command is not in `mcp_allowed_commands`."""


def check_credentials_shape(transport: str, credentials: dict[str, Any] | None) -> None:
    """Write-only secrets: {'headers': {...}} for http, {'env': {...}} for stdio.

    An empty dict is valid and means "clear the stored credentials"."""
    if not credentials:
        return
    allowed_key = "headers" if transport == "http" else "env"
    if set(credentials) - {allowed_key}:
        raise ValueError(f"credentials must only contain '{allowed_key}' for {transport} servers")
    values = credentials.get(allowed_key)
    if not isinstance(values, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in values.items()
    ):
        raise ValueError(f"credentials['{allowed_key}'] must be a string-to-string object")


def _allowed_commands() -> set[str]:
    return {c.strip() for c in settings.mcp_allowed_commands.split(",") if c.strip()}


def command_allowed(command: str) -> bool:
    """Allow if the allowlist is empty, else match argv[0].

    Matches the full command, its basename, or the basename's alphabetic
    stem — so `/usr/bin/python3.12` counts as `python` while `uvx` never
    matches `uv` and `server.py` does not match `python`."""
    allowed = _allowed_commands()
    if not allowed:
        return True
    command = (command or "").strip()
    if not command:
        return False
    basename = os.path.basename(command)
    if command in allowed or basename in allowed:
        return True
    stem = re.match(r"[A-Za-z]+", basename)
    return bool(stem) and stem.group(0).lower() in allowed


def require_command_allowed(command: str) -> None:
    if not command_allowed(command):
        allowed = ", ".join(sorted(_allowed_commands())) or "(any)"
        raise CommandNotAllowedError(
            f"Command '{command}' is not allowed; permitted executables: {allowed} "
            "(set MCP_ALLOWED_COMMANDS to change)"
        )


def _fernet() -> Fernet:
    # 32 bytes, urlsafe-base64 encoded = a valid Fernet key.
    digest = hashlib.sha256((settings.jwt_secret + "|mcp-credentials").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_credentials(data: dict[str, Any]) -> str:
    """Serialize + encrypt a credentials blob ({"headers": {...}} / {"env": {...}})."""
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_credentials(token: str) -> dict[str, Any]:
    """Reverse of encrypt_credentials; raises ValueError on a bad/rotated key."""
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Stored MCP credentials could not be decrypted") from exc
