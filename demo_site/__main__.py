import argparse

import uvicorn

p = argparse.ArgumentParser(description="Run the local demo site")
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=8000)
p.add_argument("--flaky", action="store_true", help="fail or stall ~1 in 4 requests")
a = p.parse_args()
if a.flaky:
    import os
    os.environ["DEMO_FLAKY"] = "1"
uvicorn.run("demo_site.app:app", host=a.host, port=a.port, log_level="warning")
