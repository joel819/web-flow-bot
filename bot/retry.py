"""Retry policy: exponential backoff with jitter and error classification."""
from __future__ import annotations

import random
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .errors import PermanentError, TransientError


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 0.5
    factor: float = 2.0
    max_delay: float = 8.0
    jitter: float = 0.1

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay < 0 or self.max_delay < 0 or self.factor < 1 or not 0 <= self.jitter < 1:
            raise ValueError("invalid retry policy values")

    def delay_after(self, attempt: int, rng: random.Random | None = None) -> float:
        """Seconds to wait after failed attempt number `attempt` (1-based)."""
        raw = min(self.base_delay * self.factor ** (attempt - 1), self.max_delay)
        if self.jitter and rng is not None:
            raw *= 1 + rng.uniform(-self.jitter, self.jitter)
        return round(max(raw, 0.0), 3)


def is_transient(exc: BaseException) -> bool:
    """Timeouts, dropped connections and explicit TransientErrors are retried.
    Everything else (bad credentials, validation, unexpected bugs) is not."""
    if isinstance(exc, PermanentError):
        return False
    return isinstance(exc, (TransientError, PlaywrightTimeout, PlaywrightError))
