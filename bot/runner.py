from __future__ import annotations

import random
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright

from .config import Config
from .errors import StepFailed
from .retry import is_transient
from .runlog import RunLog, now_iso
from .screenshots import Shots
from .steps import Context, Step, build_steps


def run_step(step: Step, ctx: Context, rec, shots: Shots, cfg: Config,
             sleep: Callable[[float], None], rng: random.Random) -> None:
    """Run one step with retries. Records every attempt; raises StepFailed."""
    policy = cfg.retry
    t_step = time.perf_counter()
    last: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        t0 = time.perf_counter()
        try:
            if attempt > 1 and step.recover:
                step.recover(ctx)
            step.run(ctx)
        except Exception as exc:  # noqa: BLE001 - classified below
            last = exc
            transient = is_transient(exc)
            entry = {
                "n": attempt, "ok": False, "duration_ms": int((time.perf_counter() - t0) * 1000),
                "error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}",
                "retryable": transient,
                "screenshot": shots.take(ctx.page, step.name, attempt, ok=False),
            }
            if transient and attempt < policy.max_attempts:
                entry["backoff_s"] = policy.delay_after(attempt, rng)
            rec.attempts.append(entry)
            if not transient or attempt == policy.max_attempts:
                rec.status = "failed"
                rec.duration_ms = int((time.perf_counter() - t_step) * 1000)
                raise StepFailed(step.name, attempt, exc, permanent=not transient) from exc
            sleep(entry["backoff_s"])
            continue
        rec.attempts.append({
            "n": attempt, "ok": True, "duration_ms": int((time.perf_counter() - t0) * 1000),
            "screenshot": shots.take(ctx.page, step.name, attempt, ok=True),
        })
        rec.status = "passed" if attempt == 1 else "passed-after-retry"
        rec.duration_ms = int((time.perf_counter() - t_step) * 1000)
        return
    raise AssertionError("unreachable") from last


def run_flow(cfg: Config, *, steps: list[Step] | None = None,
             sleep: Callable[[float], None] = time.sleep, seed: int | None = None) -> RunLog:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(cfg.runs_dir) / run_id
    n = 1
    while run_dir.exists():                      # two runs in the same second
        n += 1
        run_dir = Path(cfg.runs_dir) / f"{run_id}-{n}"
    shots = Shots(run_dir)
    log = RunLog(run_dir.name, cfg.base_url, cfg.retry.max_attempts)
    rng = random.Random(seed)

    with sync_playwright() as pw:
        launch = {"headless": cfg.headless}
        if cfg.chromium_executable_path:
            launch["executable_path"] = cfg.chromium_executable_path
        browser = pw.chromium.launch(**launch)
        try:
            page = browser.new_context(viewport={"width": 900, "height": 760}).new_page()
            page.set_default_timeout(cfg.step_timeout_ms)
            ctx = Context(page, cfg)
            try:
                for step in steps or build_steps():
                    run_step(step, ctx, log.step(step.name), shots, cfg, sleep, rng)
                log.success, log.reference = True, ctx.state.get("reference")
            except StepFailed as exc:
                log.error = str(exc)
        finally:
            browser.close()
            log.finished_at = now_iso()
            log.write(run_dir)
    return log
