"""HR document vault: encrypted storage, role-based access, OCR search, append-only audit log."""
import hashlib
import html
import io
import json
import mimetypes
import os
import re
import threading
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from . import crypto
from .auth import current_user, require
from .db import DATA_DIR, ex, get_conn, now, now_s, q, q1, tx
from .ocr import extract_text

router = APIRouter(prefix="/api/vault", tags=["vault"])
STORE_DIR = os.path.join(DATA_DIR, "vault")
DOC_TYPES = {"offer_letter": "Offer letter", "id_proof": "ID proof", "appraisal": "Appraisal", "other": "Other"}
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".docx", ".txt"}

# ------------------------------------------------------------------ audit log (hash-chained, append-only)

_audit_lock = threading.Lock()


def audit(user, action, doc_id=None, detail=None, outcome="allowed"):
    with _audit_lock, tx():
        last = q1("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1")
        prev = last["hash"] if last else "0" * 64
        rec = {"at": now_s(), "user_id": user["id"] if user else None, "username": user["username"] if user else None,
               "role": user["role"] if user else None, "action": action, "doc_id": doc_id,
               "detail": detail if isinstance(detail, str) or detail is None else json.dumps(detail),
               "outcome": outcome}
        h = hashlib.sha256((prev + json.dumps(rec, sort_keys=True)).encode()).hexdigest()
        ex("""INSERT INTO audit_log(at, user_id, username, role, action, doc_id, detail, outcome, prev_hash, hash)
              VALUES (:at,:user_id,:username,:role,:action,:doc_id,:detail,:outcome,:prev,:hash)""",
           rec | {"prev": prev, "hash": h})


def verify_chain():
    prev = "0" * 64
    rows = q("SELECT * FROM audit_log ORDER BY id")
    for r in rows:
        rec = {k: r[k] for k in ("at", "user_id", "username", "role", "action", "doc_id", "detail", "outcome")}
        h = hashlib.sha256((prev + json.dumps(rec, sort_keys=True)).encode()).hexdigest()
        if r["prev_hash"] != prev or r["hash"] != h:
            return {"ok": False, "broken_at": r["id"], "entries": len(rows)}
        prev = h
    return {"ok": True, "entries": len(rows)}


# ------------------------------------------------------------------ classification

RULES = {
    "offer_letter": [r"offer letter", r"pleased to offer", r"letter of offer", r"\bctc\b", r"cost to company",
                     r"joining date", r"date of joining", r"annual compensation", r"relocation bonus", r"\boffer\b"],
    "id_proof": [r"aadhaa?r", r"\bpassport\b", r"permanent account number", r"\bpan\b", r"driving licen[cs]e",
                 r"voter id", r"date of birth", r"\bdob\b", r"government of india", r"identity card", r"id proof"],
    "appraisal": [r"apprais", r"performance review", r"performance rating", r"review period", r"\bkra\b",
                  r"goals? for next", r"overall rating", r"self[- ]assessment", r"increment"],
}


def classify(text: str, filename: str) -> tuple[str, str]:
    hay = (filename.replace("_", " ").replace("-", " ") + "\n" + text).lower()
    scores = {}
    for t, pats in RULES.items():
        hits = [p for p in pats if re.search(p, hay)]
        fname_bonus = 2 if any(re.search(p, filename.lower().replace("_", " ")) for p in pats) else 0
        scores[t] = (len(hits) + fname_bonus, hits)
    best = max(scores, key=lambda k: scores[k][0])
    if scores[best][0] < 2:
        return "other", "no strong keywords found"
    words = ", ".join(h.replace("\\b", "").replace("\\", "") for h in scores[best][1][:4])
    return best, f"rule: matched {words}"


# ------------------------------------------------------------------ in-memory search index (plaintext never hits disk)

TEXT: dict[int, str] = {}


def _dek(doc):
    return crypto.unwrap(doc["wrapped_key"])


def load_text_index():
    TEXT.clear()
    for d in q("SELECT id, wrapped_key, text_enc, storage_name FROM vault_docs WHERE deleted=0"):
        if d["text_enc"]:
            TEXT[d["id"]] = crypto.decrypt_blob(_dek(d), d["text_enc"], d["storage_name"] + ":text").decode()


# ------------------------------------------------------------------ access control

def can_access(user, doc) -> bool:
    if user["role"] == "admin":
        return True
    if user["role"] == "hr":
        return doc["department"] == user["department"]
    return bool(user["employee_id"]) and doc["employee_id"] == user["employee_id"]


def scope_label(user):
    return {"admin": "All departments", "hr": f"{user['department']} department"}.get(
        user["role"], f"Your own documents ({user['employee_id'] or 'no employee ID'})")


def _retention_expired(doc):
    if not doc["retention_until"]:
        return False
    try:
        return date.fromisoformat(doc["retention_until"]) < now().date()
    except (TypeError, ValueError):
        return True


def _get_doc_checked(doc_id, user, action, allow_expired=False):
    doc = q1("SELECT * FROM vault_docs WHERE id=? AND deleted=0", (doc_id,))
    if not doc:
        audit(user, action, doc_id, "document not found", "denied")
        raise HTTPException(404, "Document not found")
    if not can_access(user, doc):
        audit(user, action, doc_id, f"role {user['role']} outside scope ({doc['department']}/{doc['employee_id']})", "denied")
        raise HTTPException(403, "Access denied: this document is outside your role's scope. The attempt has been logged.")
    if _retention_expired(doc) and not allow_expired:
        audit(user, action, doc_id, "document retention period expired", "denied")
        raise HTTPException(410, "Document retention period has expired")
    return doc


def _public(doc):
    d = {k: v for k, v in doc.items() if k not in ("wrapped_key", "text_enc", "storage_name", "sha256")}
    d["doc_type_label"] = DOC_TYPES.get(doc["doc_type"], doc["doc_type"])
    d["retention_expired"] = _retention_expired(doc)
    return d


DOC_SELECT = """SELECT v.*, e.name AS employee_name, u.name AS uploaded_by_name FROM vault_docs v
                JOIN employees e ON e.employee_id=v.employee_id LEFT JOIN users u ON u.id=v.uploaded_by"""

# ------------------------------------------------------------------ storing


def store_document(data: bytes, filename: str, employee_id: str, user, doc_type=None, retention_until=None):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"File type {ext or '?'} is not accepted")
    emp = q1("SELECT * FROM employees WHERE employee_id=?", (employee_id.strip().upper(),))
    if not emp:
        raise HTTPException(400, "Unknown employee ID")
    if user["role"] == "hr" and emp["department"] != user["department"]:
        audit(user, "upload", None, f"employee {emp['employee_id']} outside HR scope", "denied")
        raise HTTPException(403, "You can only upload documents for your own department")
    text, ocr_used = extract_text(data, filename)
    auto_type, reason = classify(text, filename)
    final_type = doc_type if doc_type in DOC_TYPES else auto_type
    storage_name = uuid.uuid4().hex + ".bin"
    dek, wrapped = crypto.new_file_key()
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(os.path.join(STORE_DIR, storage_name), "wb") as f:
        f.write(crypto.encrypt_blob(dek, data, storage_name))
    text_enc = crypto.encrypt_blob(dek, text.encode(), storage_name + ":text")
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    doc_id = ex("""INSERT INTO vault_docs(employee_id, department, doc_type, doc_type_source, type_reason, original_name,
                   mime, size, uploaded_by, uploaded_at, retention_until, storage_name, wrapped_key, sha256, ocr_used, text_enc)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (emp["employee_id"], emp["department"], final_type, "user" if doc_type in DOC_TYPES else "rule",
                 reason if doc_type not in DOC_TYPES else "set at upload", os.path.basename(filename), mime, len(data),
                 user["id"], now_s(), retention_until or None, storage_name, wrapped,
                 hashlib.sha256(data).hexdigest(), int(ocr_used), text_enc))
    TEXT[doc_id] = text
    audit(user, "upload", doc_id, {"file": os.path.basename(filename), "employee": emp["employee_id"],
                                   "type": final_type, "ocr": bool(ocr_used)})
    return doc_id


def read_plain(doc) -> bytes:
    with open(os.path.join(STORE_DIR, doc["storage_name"]), "rb") as f:
        blob = f.read()
    return crypto.decrypt_blob(_dek(doc), blob, doc["storage_name"])


# ------------------------------------------------------------------ watermarking

def watermark(data: bytes, doc, user) -> bytes:
    stamp = f"CONFIDENTIAL - {user['username']} - {now_s().replace('T', ' ')} IST - doc #{doc['id']}"
    try:
        if doc["mime"].startswith("image/"):
            from PIL import Image, ImageDraw, ImageFont
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            dr = ImageDraw.Draw(layer)
            size = max(16, img.width // 40)
            font = ImageFont.load_default(size=size)
            for y in range(0, img.height, size * 6):
                dr.text((size, y + size), stamp, fill=(200, 0, 0, 90), font=font)
            out = io.BytesIO()
            Image.alpha_composite(img, layer).convert("RGB").save(out, format="PNG" if doc["mime"] == "image/png" else "JPEG")
            return out.getvalue()
        if doc["mime"] == "application/pdf":
            from pypdf import PdfReader, PdfWriter
            from reportlab.pdfgen import canvas
            reader = PdfReader(io.BytesIO(data))
            writer = PdfWriter()
            for page in reader.pages:
                w, h = float(page.mediabox.width), float(page.mediabox.height)
                buf = io.BytesIO()
                c = canvas.Canvas(buf, pagesize=(w, h))
                c.setFillColorRGB(0.8, 0, 0); c.setFillAlpha(0.25); c.setFont("Helvetica", 11)
                c.saveState(); c.translate(w / 2, h / 2); c.rotate(35)
                for dy in range(-int(h), int(h), 90):
                    c.drawCentredString(0, dy, stamp)
                c.restoreState(); c.save()
                page.merge_page(PdfReader(buf).pages[0])
                writer.add_page(page)
            out = io.BytesIO(); writer.write(out)
            return out.getvalue()
    except Exception:  # noqa: BLE001 - never block a download because of the watermark
        return data
    return data


# ------------------------------------------------------------------ API

@router.get("/meta")
def vault_meta(user=Depends(current_user)):
    return {"doc_types": DOC_TYPES, "scope": scope_label(user), "can_upload": user["role"] in ("hr", "admin"),
            "is_admin": user["role"] == "admin", "key_fingerprint": crypto.key_fingerprint() if user["role"] == "admin" else None}


@router.get("/employees")
def employees(qs: str = "", user=Depends(require("hr", "admin"))):
    sql, params = "SELECT * FROM employees WHERE (employee_id LIKE ? OR name LIKE ?)", [f"%{qs}%", f"%{qs}%"]
    if user["role"] == "hr":
        sql += " AND department=?"; params.append(user["department"])
    return {"employees": q(sql + " ORDER BY employee_id LIMIT 50", params)}


@router.get("/docs")
def list_docs(employee_id: str | None = None, doc_type: str | None = None, user=Depends(current_user)):
    where, params = ["v.deleted=0"], []
    if user["role"] == "hr":
        where.append("v.department=?"); params.append(user["department"])
    elif user["role"] != "admin":
        where.append("v.employee_id=?"); params.append(user["employee_id"] or "-")
    if employee_id:
        where.append("v.employee_id=?"); params.append(employee_id.upper())
    if doc_type:
        where.append("v.doc_type=?"); params.append(doc_type)
    rows = q(DOC_SELECT + " WHERE " + " AND ".join(where) + " ORDER BY v.uploaded_at DESC LIMIT 500", params)
    return {"docs": [_public(r) for r in rows], "scope": scope_label(user)}


@router.post("/docs")
async def upload(file: UploadFile = File(...), employee_id: str = Form(...), doc_type: str = Form(""),
                 retention_until: str = Form(""), user=Depends(require("hr", "admin"))):
    data = await file.read()
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "File is empty or larger than 20 MB")
    if retention_until:
        try:
            date.fromisoformat(retention_until)
        except ValueError:
            raise HTTPException(400, "Retention date must be YYYY-MM-DD")
    doc_id = store_document(data, file.filename or "upload", employee_id, user, doc_type or None, retention_until or None)
    return {"doc": _public(q1(DOC_SELECT + " WHERE v.id=?", (doc_id,)))}


@router.get("/docs/{doc_id}")
def doc_meta(doc_id: int, user=Depends(current_user)):
    doc = _get_doc_checked(doc_id, user, "view")
    full = q1(DOC_SELECT + " WHERE v.id=?", (doc_id,))
    audit(user, "view", doc_id, "metadata and text")
    return {"doc": _public(full), "text": TEXT.get(doc_id, "")}


@router.get("/docs/{doc_id}/file")
def doc_file(doc_id: int, download: bool = False, user=Depends(current_user)):
    action = "download" if download else "view"
    doc = _get_doc_checked(doc_id, user, action)
    data = read_plain(doc)
    if download:
        data = watermark(data, doc, user)
    audit(user, action, doc_id, doc["original_name"] + (" (watermarked)" if download else ""))
    disp = "attachment" if download else "inline"
    return Response(data, media_type=doc["mime"], headers={
        "Content-Disposition": f'{disp}; filename="{doc["original_name"]}"', "Cache-Control": "no-store"})


class DocPatch(BaseModel):
    doc_type: str | None = None
    retention_until: str | None = None


@router.patch("/docs/{doc_id}")
def update_doc(doc_id: int, body: DocPatch, user=Depends(require("hr", "admin"))):
    doc = _get_doc_checked(doc_id, user, "update", allow_expired=body.retention_until is not None)
    if body.doc_type:
        if body.doc_type not in DOC_TYPES:
            raise HTTPException(400, "Unknown document type")
    if body.retention_until:
        try:
            date.fromisoformat(body.retention_until)
        except ValueError:
            raise HTTPException(400, "Retention date must be YYYY-MM-DD")

    if body.doc_type:
        ex("UPDATE vault_docs SET doc_type=?, doc_type_source='user', type_reason=? WHERE id=?",
           (body.doc_type, f"corrected by {user['username']}", doc_id))
        audit(user, "update", doc_id, f"type {doc['doc_type']} -> {body.doc_type}")
    if body.retention_until is not None:
        ex("UPDATE vault_docs SET retention_until=? WHERE id=?", (body.retention_until or None, doc_id))
        audit(user, "update", doc_id, f"retention -> {body.retention_until or 'none'}")
    return {"doc": _public(q1(DOC_SELECT + " WHERE v.id=?", (doc_id,)))}


def _snippets(text, terms, phrase, n=2, width=90):
    flat = re.sub(r"\s+", " ", text)
    low = flat.lower()
    anchors = []
    if phrase:
        anchors = [m.start() for m in re.finditer(re.escape(phrase), low)]
    if not anchors:
        for t in terms:
            anchors += [m.start() for m in re.finditer(re.escape(t), low)][:1]
    out, used = [], -10**9
    for a in sorted(anchors):
        if a - used < width * 2:
            continue
        s, e = max(0, a - width), min(len(flat), a + width + len(phrase or ""))
        frag = html.escape(flat[s:e])
        pats = sorted({phrase, *terms} - {""}, key=len, reverse=True)
        frag = re.sub("(" + "|".join(re.escape(html.escape(p)) for p in pats) + ")", r"<mark>\1</mark>", frag, flags=re.I)
        out.append(("… " if s else "") + frag + (" …" if e < len(flat) else ""))
        used = a
        if len(out) >= n:
            break
    return out


@router.get("/search")
def search(qs: str, user=Depends(current_user)):
    query = qs.strip()
    if len(query) < 2:
        raise HTTPException(400, "Type at least two characters")
    phrase = re.sub(r"\s+", " ", query.strip('"')).lower()
    terms = [t for t in re.findall(r"\w+", phrase) if len(t) > 1]
    visible = {d["id"]: d for d in q(DOC_SELECT + " WHERE v.deleted=0")
               if can_access(user, d) and not _retention_expired(d)}
    results = []
    for doc_id, d in visible.items():
        text = TEXT.get(doc_id, "")
        hay = re.sub(r"\s+", " ", (text + " " + d["original_name"].replace("_", " "))).lower()
        if phrase in hay:
            score = 100 + hay.count(phrase)
        elif terms and all(t in hay for t in terms):
            score = sum(hay.count(t) for t in terms)
        else:
            continue
        results.append({"doc": _public(d), "score": score, "snippets": _snippets(text, terms, phrase) or
                        [html.escape(d["original_name"])]})
    results.sort(key=lambda r: -r["score"])
    audit(user, "search", None, {"query": query, "results": len(results)})
    return {"results": results, "scope": scope_label(user)}


@router.get("/audit")
def audit_list(action: str | None = None, limit: int = 200, user=Depends(require("admin"))):
    sql, params = "SELECT * FROM audit_log", []
    if action:
        sql += " WHERE action=? OR outcome=?"; params += [action, action]
    return {"entries": q(sql + " ORDER BY id DESC LIMIT ?", params + [min(limit, 1000)]), "chain": verify_chain()}


@router.get("/storage/{doc_id}")
def storage_proof(doc_id: int, user=Depends(require("admin"))):
    """Shows what is actually on disk for a document: ciphertext, not the file."""
    doc = _get_doc_checked(doc_id, user, "storage-inspect")
    path = os.path.join(STORE_DIR, doc["storage_name"])
    with open(path, "rb") as f:
        raw = f.read()
    plain = read_plain(doc)
    import math
    from collections import Counter
    cnt = Counter(raw)
    entropy = -sum(c / len(raw) * math.log2(c / len(raw)) for c in cnt.values())
    printable = sum(32 <= b < 127 for b in raw[:2000]) / max(1, min(2000, len(raw)))
    audit(user, "storage-inspect", doc_id, "viewed ciphertext proof")
    return {"path_on_disk": os.path.relpath(path, DATA_DIR), "stored_bytes": len(raw), "original_bytes": len(plain),
            "disk_head_hex": raw[:48].hex(" "), "original_head_hex": plain[:48].hex(" "),
            "disk_head_text": raw[:48].decode("latin-1").encode("unicode_escape").decode(),
            "original_head_text": plain[:48].decode("latin-1").encode("unicode_escape").decode(),
            "entropy_bits_per_byte": round(entropy, 3), "printable_ratio": round(printable, 3),
            "cipher": "AES-256-GCM, per-file data key wrapped by master key", "key_fingerprint": crypto.key_fingerprint(),
            "sha256_matches": hashlib.sha256(plain).hexdigest() == doc["sha256"]}


# ---- two-person deletion

class DeleteReq(BaseModel):
    reason: str = ""


@router.post("/docs/{doc_id}/delete-request")
def request_delete(doc_id: int, body: DeleteReq, user=Depends(require("hr", "admin"))):
    _get_doc_checked(doc_id, user, "delete-request", allow_expired=True)
    if q1("SELECT id FROM vault_delete_requests WHERE doc_id=? AND status='pending'", (doc_id,)):
        raise HTTPException(400, "A deletion request is already waiting for approval")
    rid = ex("INSERT INTO vault_delete_requests(doc_id, requested_by, requested_at, reason) VALUES (?,?,?,?)",
             (doc_id, user["id"], now_s(), body.reason))
    audit(user, "delete-request", doc_id, body.reason or "no reason given")
    return {"id": rid}


@router.get("/delete-requests")
def delete_requests(user=Depends(require("hr", "admin"))):
    rows = q("""SELECT r.*, u.name AS requested_by_name, a.name AS approved_by_name, v.original_name, v.department
                FROM vault_delete_requests r JOIN users u ON u.id=r.requested_by JOIN vault_docs v ON v.id=r.doc_id
                LEFT JOIN users a ON a.id=r.approved_by ORDER BY r.id DESC LIMIT 100""")
    if user["role"] == "hr":
        rows = [r for r in rows if r["department"] == user["department"]]
    return {"requests": rows}


class Decision(BaseModel):
    approve: bool


@router.post("/delete-requests/{rid}/decide")
def decide_delete(rid: int, body: Decision, user=Depends(require("admin"))):
    r = q1("SELECT * FROM vault_delete_requests WHERE id=? AND status='pending'", (rid,))
    if not r:
        raise HTTPException(404, "No pending request")
    if r["requested_by"] == user["id"]:
        audit(user, "delete-approve", r["doc_id"], "same person cannot approve own request", "denied")
        raise HTTPException(403, "A second person must approve deletion (you made this request)")
    ex("UPDATE vault_delete_requests SET status=?, approved_by=?, approved_at=? WHERE id=?",
       ("approved" if body.approve else "rejected", user["id"], now_s(), rid))
    if body.approve:
        doc = q1("SELECT * FROM vault_docs WHERE id=?", (r["doc_id"],))
        try:
            os.remove(os.path.join(STORE_DIR, doc["storage_name"]))  # crypto-shred: ciphertext gone,
        except OSError:
            pass
        ex("UPDATE vault_docs SET deleted=1, wrapped_key=X'', text_enc=NULL WHERE id=?", (r["doc_id"],))  # key gone too
        TEXT.pop(r["doc_id"], None)
    audit(user, "delete-approve" if body.approve else "delete-reject", r["doc_id"], f"request #{rid}")
    return {"ok": True}
