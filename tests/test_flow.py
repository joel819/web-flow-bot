import json

from bot.runner import run_flow


def test_happy_path(site, make_cfg, no_sleep):
    cfg = make_cfg(site)
    log = run_flow(cfg, sleep=no_sleep)
    assert log.success and log.reference.startswith("WFB-")
    assert [s.status for s in log.steps] == ["passed"] * 5
    assert len(site.app.state.store) == 1
    assert site.app.state.store.get(log.reference).payload["full_name"] == "Grace Hopper"


def test_artifacts_written(site, make_cfg, no_sleep):
    cfg = make_cfg(site)
    log = run_flow(cfg, sleep=no_sleep)
    run_dir = cfg.runs_dir / log.run_id
    shots = sorted(p.name for p in run_dir.glob("*.png"))
    assert len(shots) == 5 and shots[0].startswith("01-login")
    data = json.loads((run_dir / "run.json").read_text())
    assert data["success"] is True and data["reference"] == log.reference
    assert [s["name"] for s in data["steps"]] == ["login", "open-form", "fill-form", "submit", "verify"]
    for step in data["steps"]:
        assert step["attempts"][0]["screenshot"] in shots
        assert step["attempts"][0]["duration_ms"] >= 0


def test_run_log_never_contains_password(site, make_cfg, no_sleep):
    cfg = make_cfg(site)
    log = run_flow(cfg, sleep=no_sleep)
    text = (cfg.runs_dir / log.run_id / "run.json").read_text()
    assert cfg.password not in text
    assert "password" not in repr(cfg).lower() or cfg.password not in repr(cfg)
