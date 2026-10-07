"""Failure injection: randomly slow or failing requests."""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

# Paths that are never disturbed (assets, health, introspection).
EXEMPT_PREFIXES = ("/static", "/health", "/api", "/__", "/favicon")


@dataclass
class Flaky:
    enabled: bool = False
    rate: float = 0.25           # 1 in 4 by default
    delay: float = 6.0           # seconds a "slow" response stalls
    seed: int | None = None
    rng: random.Random = field(init=False)
    forced: list[str] = field(default_factory=list)   # deterministic queue (tests)
    incidents: dict[str, int] = field(default_factory=lambda: {"slow": 0, "error": 0, "error_after": 0})

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def applies(self, path: str) -> bool:
        return not path.startswith(EXEMPT_PREFIXES)

    def roll(self, path: str) -> str | None:
        """Decide this request's fate: None, 'slow', 'error' or 'error_after'."""
        if not self.applies(path):
            return None
        if self.forced:
            kind = self.forced.pop(0)
            kind = None if kind == "ok" else kind
        elif self.enabled and self.rng.random() < self.rate:
            kind = self.rng.choice(["slow", "error", "error"])
        else:
            kind = None
        if kind:
            self.incidents[kind] += 1
        return kind

    async def stall(self) -> None:
        await asyncio.sleep(self.delay)
