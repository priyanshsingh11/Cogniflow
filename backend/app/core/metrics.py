"""Process-local metrics for the /metrics endpoint (phase 8 extras).

Global counters only — no tenant data — so the endpoint can stay open for
Prometheus-style scrapes like /health. Database-derived stats (run success
rate, llm call counts) are queried live by the handler; these counters cover
what only the request path sees.
"""

import itertools
import time
from collections import Counter

_STARTED_AT = time.time()
_REQUESTS: Counter[str] = Counter()  # key: status class, e.g. "2xx"
_RATE_LIMITED = itertools.count()


def record_request(status_code: int) -> None:
    _REQUESTS[f"{status_code // 100}xx"] += 1


def record_rate_limited() -> None:
    next(_RATE_LIMITED)


def uptime_seconds() -> float:
    return time.time() - _STARTED_AT


def render(extra_lines: list[str] | None = None) -> str:
    """Prometheus text exposition format (v0.0.4)."""
    lines = [
        "# HELP cogniflow_uptime_seconds Seconds since this process started.",
        "# TYPE cogniflow_uptime_seconds gauge",
        f"cogniflow_uptime_seconds {uptime_seconds():.3f}",
        "# HELP cogniflow_http_requests_total HTTP responses by status class (process-local).",
        "# TYPE cogniflow_http_requests_total counter",
    ]
    for status_class in sorted(_REQUESTS):
        count = _REQUESTS[status_class]
        lines.append(f'cogniflow_http_requests_total{{class="{status_class}"}} {count}')
    lines += [
        "# HELP cogniflow_rate_limited_total Requests rejected with 429 (process-local).",
        "# TYPE cogniflow_rate_limited_total counter",
        f"cogniflow_rate_limited_total {sum(_RATE_LIMITED)}",
    ]
    if extra_lines:
        lines += extra_lines
    return "\n".join(lines) + "\n"
