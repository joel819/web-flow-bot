"""The individual steps of the flow. Each takes a Context and raises on failure."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import httpx

from .config import Config
from .errors import PermanentError, TransientError, VerificationError

REFERENCE_RE = re.compile(r"^WFB-[A-Z2-9]{8}$")


@dataclass
class Context:
    page: object
    cfg: Config
    state: dict = field(default_factory=dict)


@dataclass
class Step:
    name: str
    run: Callable[[Context], None]
    recover: Callable[[Context], None] | None = None   # re-establish state before a retry


def _raise_if_error_page(page) -> None:
    """Error pages from the site carry <body data-error="NNN">."""
    code = page.locator("body[data-error]")
    if code.count():
        status = code.first.get_attribute("data-error")
        raise TransientError(f"site returned an error page ({status})")


def login(ctx: Context) -> None:
    p = ctx.page
    p.goto(f"{ctx.cfg.base_url}/login")
    _raise_if_error_page(p)
    p.fill("#user", ctx.cfg.username)
    p.fill("#pw", ctx.cfg.password)
    p.click("#login-form button[type=submit]")
    p.wait_for_selector("#request-form, #login-error, body[data-error]")
    if p.locator("#login-error").count():
        raise PermanentError("login rejected: invalid credentials")
    _raise_if_error_page(p)


def open_form(ctx: Context) -> None:
    p = ctx.page
    p.goto(f"{ctx.cfg.base_url}/form")
    _raise_if_error_page(p)
    if not p.locator("#request-form").count():
        raise TransientError("form not shown (session lost?)")


def fill_form(ctx: Context) -> None:
    f, p = ctx.cfg.form, ctx.page
    p.fill("#full_name", str(f["full_name"]))
    p.fill("#email", str(f["email"]))
    p.select_option("#department", label=str(f["department"]))
    p.fill("#start_date", str(f["start_date"]))
    p.fill("#notes", str(f.get("notes", "")))
    p.set_checked("#newsletter", bool(f.get("newsletter", False)))


def submit(ctx: Context) -> None:
    p = ctx.page
    p.click("#submit")
    p.wait_for_selector("#reference, .field-error, body[data-error]")
    if p.locator(".field-error").count():
        errs = [e.strip() for e in p.locator(".field-error").all_inner_texts()]
        raise PermanentError(f"form rejected by site: {errs}")
    _raise_if_error_page(p)
    ctx.state["reference"] = p.locator("#reference").inner_text().strip()


def verify(ctx: Context) -> None:
    """Success means the confirmation page shows a well-formed reference AND the
    echoed details match what we submitted AND (optionally) the server agrees."""
    p, f = ctx.page, ctx.cfg.form
    ref = p.locator("#reference").inner_text().strip()
    if not REFERENCE_RE.match(ref):
        raise VerificationError(f"malformed reference number: {ref!r}")
    name, email = p.locator("#c-name").inner_text().strip(), p.locator("#c-email").inner_text().strip()
    if name != str(f["full_name"]).strip() or email != str(f["email"]).strip():
        raise VerificationError("confirmation page does not echo the submitted details")
    if ctx.cfg.verify_via_api:
        try:
            r = httpx.get(f"{ctx.cfg.base_url}/api/submissions/{ref}", timeout=5)
        except httpx.HTTPError as exc:
            raise TransientError(f"could not cross-check reference: {exc}") from exc
        if r.status_code != 200 or r.json().get("full_name") != str(f["full_name"]).strip():
            raise VerificationError(f"server has no matching record for {ref}")
    ctx.state["reference"] = ref


def build_steps() -> list[Step]:
    # A failed submit leaves the page on an error screen, so the retry first
    # re-opens and re-fills the form. The server dedupes, so re-submitting is safe.
    def redo_form(ctx: Context) -> None:
        open_form(ctx)
        fill_form(ctx)

    return [
        Step("login", login),
        Step("open-form", open_form, recover=None),
        Step("fill-form", fill_form, recover=open_form),
        Step("submit", submit, recover=redo_form),
        Step("verify", verify),
    ]
