from bot.retry import RetryPolicy
from bot.runner import run_flow
from demo_site.flaky import Flaky


def attempts(log, name):
    return next(s for s in log.steps if s.name == name).attempts


def test_recovers_from_503_on_login(site, make_cfg, no_sleep):
    site.flaky.forced = ["error", "error"]          # GET /login fails twice
    log = run_flow(make_cfg(site), sleep=no_sleep)
    assert log.success
    assert len(attempts(log, "login")) == 3
    assert [a["ok"] for a in attempts(log, "login")] == [False, False, True]
    assert len(no_sleep.__self__) == 2               # slept between the failed attempts only


def test_slow_response_times_out_then_succeeds(site, make_cfg, no_sleep):
    site.flaky.forced = ["slow"]                     # stalls 2.5s > 1.5s step timeout
    log = run_flow(make_cfg(site), sleep=no_sleep)
    assert log.success
    first = attempts(log, "login")[0]
    assert not first["ok"] and "Timeout" in first["error"]


def test_lost_submit_response_does_not_duplicate_the_record(site, make_cfg, no_sleep):
    # requests: GET /login, POST /login, GET /form (login redirect), GET /form (open-form),
    # then POST /submit, which the site processes before answering 503.
    site.flaky.forced = ["ok", "ok", "ok", "ok", "error_after"]
    log = run_flow(make_cfg(site), sleep=no_sleep)
    assert log.success
    assert len(attempts(log, "submit")) == 2
    assert len(site.app.state.store) == 1            # the retry hit the dedupe path
    assert site.app.state.store.get(log.reference) is not None


def test_gives_up_after_max_attempts(site, make_cfg, no_sleep):
    site.flaky.forced = ["error"] * 10
    cfg = make_cfg(site, retry=RetryPolicy(max_attempts=3, base_delay=0.01, jitter=0))
    log = run_flow(cfg, sleep=no_sleep)
    assert not log.success and "gave up after 3 attempts" in log.error
    assert len(attempts(log, "login")) == 3
    assert [s.name for s in log.steps] == ["login"]   # later steps never ran


def test_random_flakiness_with_seed(make_site, make_cfg, no_sleep):
    site = make_site(flaky=Flaky(enabled=True, rate=0.25, delay=2.5, seed=3))
    cfg = make_cfg(site, retry=RetryPolicy(max_attempts=8, base_delay=0.01, jitter=0))
    log = run_flow(cfg, sleep=no_sleep)
    assert log.success
    assert sum(site.flaky.incidents.values()) >= 1    # it really was flaky
