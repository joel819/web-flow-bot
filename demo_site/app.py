"""Local demo site: login -> form -> confirmation, with optional flakiness."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .flaky import Flaky
from .store import Store

HERE = Path(__file__).parent
DEPARTMENTS = ["Sales", "Support", "Engineering", "Finance"]


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).lower() in {"1", "true", "yes", "on"}


def create_app(
    *,
    username: str | None = None,
    password: str | None = None,
    flaky: Flaky | None = None,
    control: bool | None = None,
) -> FastAPI:
    username = username or os.getenv("DEMO_USERNAME", "demo")
    password = password or os.getenv("DEMO_PASSWORD", "demo-pass-123")
    if flaky is None:
        seed = os.getenv("DEMO_FLAKY_SEED")
        flaky = Flaky(
            enabled=_env_bool("DEMO_FLAKY"),
            rate=float(os.getenv("DEMO_FLAKY_RATE", "0.25")),
            delay=float(os.getenv("DEMO_FLAKY_DELAY", "6")),
            seed=int(seed) if seed else None,
        )
    control = _env_bool("DEMO_CONTROL") if control is None else control

    app = FastAPI(title="WFB demo site", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    store = Store()
    sessions: dict[str, str] = {}
    state = {"corrupt_confirmation": False}
    app.state.store, app.state.flaky, app.state.sessions = store, flaky, sessions

    def render(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, ctx, status_code=status)

    def error_page(request: Request, status: int, title: str, message: str) -> HTMLResponse:
        return render(request, "error.html", status, title=title, message=message, code=status)

    def current_user(request: Request) -> str | None:
        return sessions.get(request.cookies.get("wfb_session", ""))

    # -- flakiness ---------------------------------------------------------
    @app.middleware("http")
    async def inject_failures(request: Request, call_next):
        kind = flaky.roll(request.url.path)
        if kind == "slow":
            await flaky.stall()
        elif kind == "error":
            return error_page(request, 503, "Service unavailable", "Please try again shortly.")
        response = await call_next(request)
        if kind == "error_after":
            # The work happened, but the client never learns about it.
            return error_page(request, 503, "Service unavailable", "Please try again shortly.")
        return response

    # -- pages -------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/login", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        return render(request, "login.html", error=None)

    @app.post("/login")
    def login(request: Request, user: str = Form(...), pw: str = Form(...)):
        if not (secrets.compare_digest(user, username) and secrets.compare_digest(pw, password)):
            return render(request, "login.html", 401, error="Invalid username or password.")
        token = secrets.token_urlsafe(24)
        sessions[token] = user
        resp = RedirectResponse("/form", status_code=303)
        resp.set_cookie("wfb_session", token, httponly=True, samesite="lax")
        return resp

    @app.get("/form", response_class=HTMLResponse)
    def form_page(request: Request):
        if not current_user(request):
            return RedirectResponse("/login", status_code=303)
        return render(request, "form.html", departments=DEPARTMENTS, errors={}, values={})

    @app.post("/submit")
    def submit(
        request: Request,
        full_name: str = Form(""),
        email: str = Form(""),
        department: str = Form(""),
        start_date: str = Form(""),
        newsletter: str = Form(""),
        notes: str = Form(""),
    ):
        user = current_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        values = {
            "full_name": full_name.strip(), "email": email.strip(), "department": department,
            "start_date": start_date, "newsletter": bool(newsletter), "notes": notes.strip(),
        }
        errors = {}
        if not values["full_name"]:
            errors["full_name"] = "Name is required."
        if "@" not in values["email"]:
            errors["email"] = "Enter a valid email."
        if department not in DEPARTMENTS:
            errors["department"] = "Pick a department."
        if not start_date:
            errors["start_date"] = "Pick a start date."
        if errors:
            return render(request, "form.html", 422, departments=DEPARTMENTS, errors=errors, values=values)
        sub, _ = store.save(user, values)
        return RedirectResponse(f"/confirmation/{sub.reference}", status_code=303)

    @app.get("/confirmation/{reference}", response_class=HTMLResponse)
    def confirmation(request: Request, reference: str):
        if not current_user(request):
            return RedirectResponse("/login", status_code=303)
        sub = store.get(reference)
        if not sub:
            return error_page(request, 404, "Not found", "No such submission.")
        shown = "WFB-CORRUPTED" if state["corrupt_confirmation"] else sub.reference
        return render(request, "confirmation.html", reference=shown, sub=sub.payload)

    # -- machine endpoints (never flaky) ----------------------------------
    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/submissions/{reference}")
    def api_submission(reference: str):
        sub = store.get(reference)
        if not sub:
            return JSONResponse({"detail": "not found"}, status_code=404)
        return {"reference": sub.reference, **sub.payload}

    @app.get("/__stats")
    def stats():
        return {"submissions": len(store), "incidents": flaky.incidents}

    if control:
        @app.post("/__control/force")
        def force(kinds: str = ""):
            """Queue exact outcomes for the next requests, e.g. kinds=error,ok,error_after."""
            flaky.forced = [k for k in kinds.split(",") if k]
            return {"queued": flaky.forced}

        @app.post("/__control/corrupt-confirmation")
        def corrupt(on: bool = True):
            state["corrupt_confirmation"] = on
            return {"corrupt": on}

    return app


app = create_app() if os.getenv("DEMO_AUTOSTART", "1") == "1" else None
