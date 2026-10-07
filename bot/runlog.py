"""Structured JSON run log. Never records credentials."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class StepRecord:
    name: str
    attempts: list[dict] = field(default_factory=list)
    status: str = "pending"
    duration_ms: int = 0


@dataclass
class RunLog:
    run_id: str
    base_url: str
    max_attempts: int
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    success: bool = False
    reference: str | None = None
    error: str | None = None
    steps: list[StepRecord] = field(default_factory=list)

    def step(self, name: str) -> StepRecord:
        rec = StepRecord(name)
        self.steps.append(rec)
        return rec

    def to_dict(self) -> dict:
        total_attempts = sum(len(s.attempts) for s in self.steps)
        return {
            "run_id": self.run_id,
            "success": self.success,
            "reference": self.reference,
            "error": self.error,
            "base_url": self.base_url,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "max_attempts_per_step": self.max_attempts,
            "total_attempts": total_attempts,
            "retries": total_attempts - len([s for s in self.steps if s.attempts]),
            "steps": [
                {"name": s.name, "status": s.status, "duration_ms": s.duration_ms, "attempts": s.attempts}
                for s in self.steps
            ],
        }

    def write(self, directory: Path) -> Path:
        path = directory / "run.json"
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return path
