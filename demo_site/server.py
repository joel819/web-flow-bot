"""Run the demo site in a background thread (used by tests and --spawn-demo-site)."""
from __future__ import annotations

import socket
import threading
import time

import uvicorn

from .app import create_app
from .flaky import Flaky


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DemoServer:
    def __init__(self, **app_kwargs):
        self.port = free_port()
        self.app = create_app(**app_kwargs)
        cfg = uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(cfg)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def flaky(self) -> Flaky:
        return self.app.state.flaky

    def start(self) -> "DemoServer":
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError("demo site did not start")
            time.sleep(0.05)
        return self

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)
