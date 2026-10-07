import random

import pytest

from bot.config import Config
from bot.errors import PermanentError, StepFailed, TransientError
from bot.retry import RetryPolicy, is_transient
from bot.runlog import StepRecord
from bot.runner import run_step
from bot.steps import Context, Step


class FakePage:
    def screenshot(self, **kw):
        pass


def make(policy):
    cfg = Config(base_url="http://x", username="u", password="p", form={}, retry=policy)
    return Context(FakePage(), cfg), cfg


class Shots:
    def take(self, *a, **k):
        return "shot.png"


def test_delay_grows_exponentially_and_is_capped():
    p = RetryPolicy(base_delay=1, factor=2, max_delay=5, jitter=0)
    assert [p.delay_after(n) for n in (1, 2, 3, 4, 5)] == [1, 2, 4, 5, 5]


def test_jitter_stays_in_bounds():
    p = RetryPolicy(base_delay=1, factor=1, max_delay=10, jitter=0.2)
    rng = random.Random(1)
    assert all(0.8 <= p.delay_after(1, rng) <= 1.2 for _ in range(200))


@pytest.mark.parametrize("kwargs", [{"max_attempts": 0}, {"factor": 0.5}, {"jitter": 1}, {"base_delay": -1}])
def test_invalid_policy_rejected(kwargs):
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


def test_classification():
    assert is_transient(TransientError("x"))
    assert not is_transient(PermanentError("x"))
    assert not is_transient(KeyError("bug"))


def test_retries_until_success_with_backoff():
    ctx, cfg = make(RetryPolicy(max_attempts=5, base_delay=1, factor=2, max_delay=10, jitter=0))
    n = {"calls": 0}

    def flaky(_):
        n["calls"] += 1
        if n["calls"] < 3:
            raise TransientError("boom")

    sleeps, rec = [], StepRecord("s")
    run_step(Step("s", flaky), ctx, rec, Shots(), cfg, sleeps.append, random.Random(0))
    assert n["calls"] == 3 and sleeps == [1, 2]
    assert rec.status == "passed-after-retry"
    assert [a["ok"] for a in rec.attempts] == [False, False, True]


def test_permanent_error_is_not_retried():
    ctx, cfg = make(RetryPolicy(max_attempts=5))
    sleeps, rec = [], StepRecord("s")

    def bad(_):
        raise PermanentError("nope")

    with pytest.raises(StepFailed) as ei:
        run_step(Step("s", bad), ctx, rec, Shots(), cfg, sleeps.append, random.Random(0))
    assert ei.value.permanent and len(rec.attempts) == 1 and sleeps == []


def test_recover_runs_before_each_retry_only():
    ctx, cfg = make(RetryPolicy(max_attempts=3, base_delay=0, jitter=0))
    seen = []

    def run(_):
        seen.append("run")
        if seen.count("run") < 3:
            raise TransientError("x")

    run_step(Step("s", run, recover=lambda _: seen.append("recover")), ctx, StepRecord("s"),
             Shots(), cfg, lambda s: None, random.Random(0))
    assert seen == ["run", "recover", "run", "recover", "run"]
