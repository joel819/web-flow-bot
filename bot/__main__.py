from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigError, load_config
from .runner import run_flow


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bot", description="Run the login -> form -> confirm flow.")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--base-url")
    ap.add_argument("--runs-dir")
    ap.add_argument("--max-attempts", type=int, help="override retry.max_attempts")
    ap.add_argument("--spawn-demo-site", action="store_true", help="start the local demo site for this run")
    ap.add_argument("--flaky", action="store_true", help="with --spawn-demo-site: fail/stall ~1 in 4 requests")
    ap.add_argument("--seed", type=int, help="seed for the demo site's failures and the retry jitter")
    a = ap.parse_args(argv)

    try:
        cfg = load_config(a.config, a.env_file, base_url=a.base_url, runs_dir=a.runs_dir,
                          headless=False if a.headed else None)
        if a.max_attempts:
            from dataclasses import replace
            cfg.retry = replace(cfg.retry, max_attempts=a.max_attempts)
    except (ConfigError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    server = None
    if a.spawn_demo_site:
        from demo_site.flaky import Flaky
        from demo_site.server import DemoServer
        server = DemoServer(username=cfg.username, password=cfg.password,
                            flaky=Flaky(enabled=a.flaky, delay=cfg.step_timeout_ms / 1000 + 2, seed=a.seed))
        server.start()
        cfg.base_url = server.url
    try:
        log = run_flow(cfg, seed=a.seed)
    finally:
        if server:
            server.stop()

    for s in log.steps:
        tries = len(s.attempts)
        print(f"  {s.status:<18} {s.name:<10} {tries} attempt{'s' if tries != 1 else ''}  {s.duration_ms} ms")
    print(json.dumps({"success": log.success, "reference": log.reference, "run_dir": f"{cfg.runs_dir}/{log.run_id}"}))
    if log.error:
        print(log.error, file=sys.stderr)
    return 0 if log.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
