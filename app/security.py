"""Deployment hardening.

Three things a public deployment needs that a local demo does not:

* reply headers that stop a browser from being clever (no MIME sniffing, no
  framing, no referrer leak, and a CSP that only permits this app's own files),
* a brake on password guessing, so /api/auth/login is not an unlimited oracle,
* sessions that actually expire on the server, not just in the cookie.

Everything here is driven by environment variables so a local demo runs exactly
as before. Nothing in this module knows about any specific screen.
"""
import os
import threading
import time
from collections import defaultdict

from fastapi import Request

# ---------------------------------------------------------------- headers

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# The booking page (/book/...) is deliberately one self-contained file with its
# own inline style and script, so it needs 'unsafe-inline' for those. Every other
# page ships its code as a separate file and gets the strict form.
_CSP_STRICT = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; "
    "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
_CSP_INLINE_PAGE = _CSP_STRICT.replace("script-src 'self';", "script-src 'self' 'unsafe-inline';")


def csp_for(path: str) -> str:
    return _CSP_INLINE_PAGE if path.startswith("/book/") else _CSP_STRICT


def install(app):
    """Add the reply headers to every response."""

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in BASE_HEADERS.items():
            response.headers.setdefault(name, value)
        response.headers.setdefault("Content-Security-Policy", csp_for(request.url.path))
        # Only meaningful over TLS, and harmful to send over plain HTTP.
        secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        if secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


# ---------------------------------------------------------------- login throttle

MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "5"))
LOCK_SECONDS = int(os.environ.get("LOGIN_LOCK_SECONDS", "60"))
_MAX_TRACKED = 5000

_failures: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
_lock = threading.Lock()


def _prune() -> None:
    if len(_failures) <= _MAX_TRACKED:
        return
    now = time.time()
    for key in [k for k, (_, until) in _failures.items() if until and until < now]:
        _failures.pop(key, None)


def login_wait(key: str) -> int:
    """Seconds the caller must wait, or 0 if they may try now."""
    with _lock:
        count, until = _failures.get(key, (0, 0.0))
        if until and time.time() < until:
            return int(until - time.time()) + 1
        if until and time.time() >= until:
            _failures.pop(key, None)
        return 0


def note_failure(key: str) -> None:
    with _lock:
        count, _ = _failures.get(key, (0, 0.0))
        count += 1
        _failures[key] = (count, time.time() + LOCK_SECONDS if count >= MAX_FAILURES else 0.0)
        _prune()


def note_success(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def attempts_left(key: str) -> int:
    with _lock:
        count, _ = _failures.get(key, (0, 0.0))
        return max(0, MAX_FAILURES - count)


def client_key(username: str, request: Request) -> str:
    host = request.client.host if request.client else "-"
    return f"{username.strip().lower()}|{host}"


# ---------------------------------------------------------------- sessions

SESSION_HOURS = float(os.environ.get("SESSION_HOURS", "12"))


def secure_cookie() -> bool:
    """Set the Secure flag when the deployment is served over HTTPS."""
    return os.environ.get("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes") or (
        os.environ.get("PUBLIC_BASE_URL", "").startswith("https://")
    )
