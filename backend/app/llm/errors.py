"""Provider-agnostic error types. The gateway decides what to do per type."""


class LLMError(Exception):
    """Base class for every failure of a single model call."""


class RateLimitError(LLMError):
    """Provider returned 429. Don't retry this model; move to the next one."""


class ProviderUnavailableError(LLMError):
    """Timeout, network failure or 5xx. Worth one retry with backoff."""


class ProviderRejectedError(LLMError):
    """Bad request, bad key or unknown model. Retrying this model is pointless."""


class AllModelsFailedError(LLMError):
    """Every model in the chain failed or the attempt cap was hit."""

    def __init__(self, attempts: list) -> None:
        super().__init__(f"all models failed after {len(attempts)} attempt(s)")
        self.attempts = attempts
