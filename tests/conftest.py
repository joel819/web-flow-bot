import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import Config  # noqa: E402
from bot.retry import RetryPolicy  # noqa: E402
from demo_site.flaky import Flaky  # noqa: E402
from demo_site.server import DemoServer  # noqa: E402

USER, PASSWORD = "demo", "s3cret-test-pw"


@pytest.fixture
def make_site():
    servers = []

    def make(**kw):
        kw.setdefault("flaky", Flaky(enabled=False, delay=2.5))
        s = DemoServer(username=USER, password=PASSWORD, control=True, **kw).start()
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.stop()


@pytest.fixture
def site(make_site):
    return make_site()


@pytest.fixture
def make_cfg(tmp_path):
    def make(site, **kw):
        base = dict(
            base_url=site.url, username=USER, password=PASSWORD,
            form={"full_name": "Grace Hopper", "email": "grace@example.com", "department": "Engineering",
                  "start_date": "2026-11-02", "newsletter": True, "notes": "test"},
            retry=RetryPolicy(max_attempts=4, base_delay=0.01, max_delay=0.05, jitter=0),
            runs_dir=tmp_path / "runs", headless=True, step_timeout_ms=1500,
            chromium_executable_path=os.getenv("WFB_CHROMIUM_PATH"),
        )
        base.update(kw)
        return Config(**base)
    return make


@pytest.fixture
def no_sleep():
    calls = []
    return calls.append
