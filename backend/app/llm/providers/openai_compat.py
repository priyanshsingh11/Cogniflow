import time

import httpx

from app.llm.base import Provider
from app.llm.errors import ProviderRejectedError, ProviderUnavailableError, RateLimitError
from app.llm.types import LLMResponse, Message


class OpenAICompatProvider(Provider):
    """Shared adapter for vendors that speak the OpenAI chat-completions API."""

    name = ""
    base_url = ""

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}", **(extra_headers or {})}

    async def chat(self, model: str, messages: list[Message], **params) -> LLMResponse:
        payload = {"model": model, "messages": [m.to_dict() for m in messages]}
        payload.update({k: v for k, v in params.items() if v is not None})

        started = time.monotonic()
        try:
            resp = await self._client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=self._headers
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"{self.name}: timeout") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(f"{self.name}: {type(exc).__name__}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if resp.status_code == 429:
            raise RateLimitError(f"{self.name}: rate limited")
        if resp.status_code == 408 or resp.status_code >= 500:
            raise ProviderUnavailableError(f"{self.name}: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise ProviderRejectedError(f"{self.name}: HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
            content = data["choices"][0]["message"].get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(f"{self.name}: malformed response") from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            provider=self.name,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
        )

    async def close(self) -> None:
        await self._client.aclose()
