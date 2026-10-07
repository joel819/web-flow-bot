from __future__ import annotations

from pathlib import Path


class Shots:
    """Numbered screenshots inside one run directory."""

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self._n = 0

    def take(self, page, step: str, attempt: int, ok: bool) -> str | None:
        self._n += 1
        name = f"{self._n:02d}-{step}-a{attempt}{'' if ok else '-failed'}.png"
        try:
            page.screenshot(path=str(self.directory / name), full_page=True, timeout=3000)
        except Exception:  # a screenshot must never mask the real outcome
            return None
        return name
