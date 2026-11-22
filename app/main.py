"""LeadDesk - one screen for back-office team leads.

Main product : task board + workload view + SOP assistant (local AI, answers only from uploaded SOPs).
Integrated   : HR document vault (encrypted, role-based, OCR search, audit log)
               interview scheduler (availability, booking links, .ics, reminders, independent feedback).
"""
import asyncio
import logging
import os

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import crypto, interviews, llm, sop, tasks, vault
from .auth import current_user
from .auth import router as auth_router
from .db import TZ_NAME, init_db, now_s, q1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("leaddesk")
STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

app = FastAPI(title="LeadDesk", version="1.0")
for r in (auth_router, tasks.router, sop.router, vault.router, interviews.router, interviews.public):
    app.include_router(r)


async def _scheduler_loop():
    while True:
        try:
            await asyncio.to_thread(interviews.tick)
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup():
    init_db()
    crypto.load_master_key()
    if os.environ.get("SEED_DEMO", "1") == "1" and not q1("SELECT id FROM users LIMIT 1"):
        from .seed import seed_all
        await asyncio.to_thread(seed_all)
    sop.INDEX.rebuild()
    vault.load_text_index()
    asyncio.create_task(_scheduler_loop())
    log.info("LeadDesk ready. Time zone: %s. AI: %s", TZ_NAME, llm.status(force=True))


@app.get("/api/health")
def health():
    return {"ok": True, "time": now_s(), "time_zone": TZ_NAME}


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
