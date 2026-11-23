"""LeadDesk - one screen for back-office team leads.

Main product : task board + workload view + SOP assistant (local AI, answers only from uploaded SOPs).
Integrated   : HR document vault (encrypted, role-based, OCR search, audit log)
               interview scheduler (availability, booking links, .ics, reminders, independent feedback).
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import crypto, forum, impact, interviews, leaves, llm, security, sop, tasks, vault
from .auth import COOKIE, current_user
from .auth import router as auth_router
from .db import TZ_NAME, init_db, now_s, q1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("leaddesk")
STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    crypto.load_master_key()
    if os.environ.get("SEED_DEMO", "1") == "1":
        from .seed import ensure_forum_demo_users, seed_all
        if not q1("SELECT id FROM users LIMIT 1"):
            await asyncio.to_thread(seed_all)
        else:
            await asyncio.to_thread(ensure_forum_demo_users)
    sop.INDEX.rebuild()
    vault.load_text_index()
    asyncio.create_task(_scheduler_loop())
    log.info("LeadDesk ready. Time zone: %s. AI: %s", TZ_NAME, llm.status(force=True))
    _warn_if_public_demo()
    yield


app = FastAPI(title="LeadDesk", version="1.0", lifespan=lifespan)
for r in (auth_router, forum.router, tasks.router, sop.router, vault.router, interviews.router, interviews.public, leaves.router):
    app.include_router(r)

# Reply headers, login throttling and session expiry. Safe defaults; driven by env.
security.install(app)


@app.middleware("http")
async def restrict_forum_demo_accounts(request, call_next):
    path = request.url.path
    allowed = path == "/api/health" or path.startswith(("/api/auth/", "/api/forum/"))
    if path.startswith("/api/") and not allowed:
        token = request.cookies.get(COOKIE) or request.headers.get("X-Session")
        if token:
            user = q1("""SELECT u.role FROM sessions s JOIN users u ON u.id=s.user_id
                          WHERE s.token=? AND u.active=1""", (token,))
            if user and user["role"] in ("tester", "developer"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "This demo account can only access the community forum"},
                )
    return await call_next(request)


async def _scheduler_loop():
    while True:
        try:
            await asyncio.to_thread(interviews.tick)
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(60)


def _warn_if_public_demo():
    """A demo build signs anyone in as the administrator. That is fine on a laptop
    and unacceptable on a public URL, so say so once, loudly, at startup."""
    demo = os.environ.get("DEMO_MODE", "1") == "1"
    base = os.environ.get("PUBLIC_BASE_URL", "")
    public = base.startswith(("http://", "https://")) and "localhost" not in base and "127.0.0.1" not in base
    if demo and public:
        log.warning(
            "DEMO_MODE is on and PUBLIC_BASE_URL is %s: the login page lists demo accounts and "
            "their password, including the administrator. Set DEMO_MODE=0 before exposing this URL.",
            base,
        )
    elif demo:
        log.info("DEMO_MODE is on: one-click demo sign-in is available (local demo build).")


@app.get("/api/health")
def health():
    return {"ok": True, "time": now_s(), "time_zone": TZ_NAME}


@app.get("/api/impact")
def impact_numbers(user=Depends(current_user)):
    """How much work the tool is actually absorbing, counted from the database."""
    return impact.compute()


@app.get("/api/proof")
def proof(user=Depends(current_user)):
    """Numbers for the 'How we know it works' panel."""
    import json
    path = os.path.join(sop.DATA_DIR, "eval_results.json")
    ev = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            ev = json.load(f)
    return {
        "ai": llm.status(),
        "eval": ev,
        "audit_chain": vault.verify_chain(),
        "vault_docs": q1("SELECT COUNT(*) AS n FROM vault_docs WHERE deleted=0")["n"],
        "scans": q1("SELECT COUNT(*) AS n FROM vault_docs WHERE deleted=0 AND ocr_used=1")["n"],
        "sop_sections": q1("SELECT COUNT(*) AS n FROM sop_chunks")["n"],
        "gaps": q1("SELECT COUNT(*) AS n FROM questions WHERE status='needs_lead'")["n"],
        "bookings": q1("SELECT COUNT(*) AS n FROM interviews WHERE status='scheduled'")["n"],
        "time_zone": TZ_NAME,
    }


@app.get("/book/{token}")
def booking_html(token: str):
    return FileResponse(os.path.join(STATIC, "book.html"))


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
