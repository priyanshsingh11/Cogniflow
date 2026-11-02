from typing import Any

import jinja2

_jinja_env = jinja2.Environment(
    undefined=jinja2.ChainableUndefined,
    autoescape=False,
)


def render_template(value: Any, context: dict[str, Any]) -> Any:
    """Recursively render jinja2 templates in strings, dicts, and lists.

    Non-string values are returned as-is. If a rendered string exactly matches
    a template expression like `{{ steps.search.output }}`, and the context
    value is a dict or list, preserve the original data type rather than
    stringifying it.
    """
    if isinstance(value, str):
        stripped = value.strip()
        # Direct object passthrough: if template is "{{ var }}" and var is non-string
        if stripped.startswith("{{") and stripped.endswith("}}") and "\n" not in stripped:
            expr = stripped[2:-2].strip()
            # If expr is a simple path (e.g. "steps.a.output" or "input.query")
            if expr and not any(op in expr for op in ("|", "+", "-", "*", "/", "%", "==", "!=")):
                try:
                    parts = expr.split(".")
                    cur: Any = context
                    found = True
                    for part in parts:
                        if isinstance(cur, dict) and part in cur:
                            cur = cur[part]
                        elif hasattr(cur, part):
                            cur = getattr(cur, part)
                        else:
                            found = False
                            break
                    if found:
                        return cur
                except Exception:
                    pass

        try:
            tmpl = _jinja_env.from_string(value)
            return tmpl.render(**context)
        except Exception:
            return value

    if isinstance(value, dict):
        return {k: render_template(v, context) for k, v in value.items()}

    if isinstance(value, list):
        return [render_template(item, context) for item in value]

    return value
