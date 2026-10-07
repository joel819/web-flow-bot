"""Configuration: non-secret settings from YAML, credentials from the environment/.env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .retry import RetryPolicy


class ConfigError(Exception):
    pass


@dataclass
class Config:
    base_url: str
    username: str
    password: str = field(repr=False)
    form: dict
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    runs_dir: Path = Path("runs")
    headless: bool = True
    step_timeout_ms: int = 4000
    chromium_executable_path: str | None = None
    verify_via_api: bool = True


def load_config(path: str | Path = "config.yaml", env_file: str | Path | None = ".env", **overrides) -> Config:
    if env_file and Path(env_file).exists():
        load_dotenv(env_file, override=False)
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    raw = yaml.safe_load(p.read_text()) or {}

    username, password = os.getenv("WFB_USERNAME"), os.getenv("WFB_PASSWORD")
    if not username or not password:
        raise ConfigError("WFB_USERNAME and WFB_PASSWORD must be set (see .env.example)")
    if not raw.get("form"):
        raise ConfigError("config 'form' section is required")

    cfg = Config(
        base_url=(os.getenv("WFB_BASE_URL") or raw.get("base_url") or "http://127.0.0.1:8000").rstrip("/"),
        username=username,
        password=password,
        form=dict(raw["form"]),
        retry=RetryPolicy(**(raw.get("retry") or {})),
        runs_dir=Path(raw.get("runs_dir", "runs")),
        headless=bool(raw.get("headless", True)),
        step_timeout_ms=int(raw.get("step_timeout_ms", 4000)),
        chromium_executable_path=os.getenv("WFB_CHROMIUM_PATH") or raw.get("chromium_executable_path"),
        verify_via_api=bool(raw.get("verify_via_api", True)),
    )
    for k, v in overrides.items():
        if v is not None:
            setattr(cfg, k, v)
    cfg.runs_dir = Path(cfg.runs_dir)
    cfg.base_url = cfg.base_url.rstrip("/")
    return cfg
