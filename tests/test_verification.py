import httpx
import pytest

from bot.config import ConfigError, load_config
from bot.runner import run_flow


def test_bad_credentials_fail_fast_without_retry(site, make_cfg, no_sleep):
    cfg = make_cfg(site, password="wrong")
    log = run_flow(cfg, sleep=no_sleep)
    assert not log.success and "permanent error" in log.error
    assert len(log.steps[0].attempts) == 1 and no_sleep.__self__ == []


def test_wrong_confirmation_reference_fails_verification(site, make_cfg, no_sleep):
    httpx.post(f"{site.url}/__control/corrupt-confirmation", params={"on": "true"}).raise_for_status()
    log = run_flow(make_cfg(site), sleep=no_sleep)
    assert not log.success
    assert "malformed reference number" in log.error
    verify = next(s for s in log.steps if s.name == "verify")
    assert len(verify.attempts) == 1                      # a mismatch is never "retried into" success


def test_site_validation_error_is_permanent(site, make_cfg, no_sleep):
    cfg = make_cfg(site, form={"full_name": "X", "email": "not-an-email", "department": "Sales",
                               "start_date": "2026-01-01"})
    log = run_flow(cfg, sleep=no_sleep)
    assert not log.success and "form rejected by site" in log.error
    assert len(site.app.state.store) == 0


def test_config_requires_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("WFB_USERNAME", raising=False)
    monkeypatch.delenv("WFB_PASSWORD", raising=False)
    cfg = tmp_path / "c.yaml"
    cfg.write_text("form: {full_name: A}\n")
    with pytest.raises(ConfigError, match="WFB_USERNAME"):
        load_config(cfg, env_file=None)


def test_config_loads_secrets_from_env_only(tmp_path, monkeypatch):
    monkeypatch.setenv("WFB_USERNAME", "u")
    monkeypatch.setenv("WFB_PASSWORD", "hunter2")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("base_url: http://h:1/\nform: {full_name: A}\nretry: {max_attempts: 2}\n")
    c = load_config(cfg, env_file=None)
    assert (c.username, c.password, c.base_url, c.retry.max_attempts) == ("u", "hunter2", "http://h:1", 2)
    assert "hunter2" not in repr(c)
