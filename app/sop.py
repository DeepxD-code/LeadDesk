"""SOP assistant: ingest PDF/DOCX into sections, retrieve, answer only from the documents.

Pipeline
  upload -> split into sections (document + heading path) -> TF-IDF index (word + character n-grams)
  question -> (translate Hindi/Gujarati to English with the local model) -> retrieve top sections
           -> gate on retrieval score -> local LLM writes an answer from those sections only
           -> answer + sources, or "not in the SOPs" -> the question lands in the Needs-lead list.
If the local model is offline the assistant still works in extractive mode (quotes the best section).
"""
import asyncio
import json
import os
import re
import threading
import uuid
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer

from . import lexicon, llm
from .auth import current_user, require
from .db import DATA_DIR, ex, notify, now_s, q, q1, tx

router = APIRouter(prefix="/api/sop", tags=["sop"])
SOP_DIR = os.path.join(DATA_DIR, "sops")

# Retrieval gates (tuned on the sample SOPs + test questions, see scripts/eval_sop.py)
MIN_SCORE = float(os.environ.get("SOP_MIN_SCORE", "0.14"))
NOT_FOUND = "NOT_IN_SOP"

# ---------------------------------------------------------------- parsing

HEADING_RE = re.compile(r"^(?:section\s+)?(\d+(?:\.\d+)*)[.)]?\s+([A-Za-z].{1,90})$", re.I)


def _is_heading_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 90 or s.endswith((".", ",", ";", ":")) and not HEADING_RE.match(s):
        return False
    if HEADING_RE.match(s) and not s.endswith("."):
        return True
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters) and len(s.split()) <= 10


def _iter_docx_blocks(doc):
    """Paragraphs and tables in document order."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def parse_docx(path):
    import docx
    doc = docx.Document(path)
    sections, path_stack, buf = [], [], []
    title = (doc.core_properties.title or "").strip()

    def flush():
        text = "\n".join(b for b in buf if b.strip()).strip()
        if text:
            sections.append((" › ".join(path_stack) or "Introduction", text))
        buf.clear()

    for block in _iter_docx_blocks(doc):
        if block.__class__.__name__ == "Table":
            for row in block.rows:
                cells = []
                for c in row.cells:
                    t = c.text.strip()
                    if t and (not cells or cells[-1] != t):
                        cells.append(t)
                if cells:
                    buf.append(" | ".join(cells))
            continue
        text = block.text.strip()
        if not text:
            continue
        style = (block.style.name or "").lower() if block.style is not None else ""
        level = None
        if style.startswith("heading"):
            m = re.search(r"(\d+)", style)
            level = int(m.group(1)) if m else 1
        elif style == "title":
            title = title or text
            continue
        elif len(text) < 90 and block.runs and all(r.bold for r in block.runs if r.text.strip()):
            level = 2
        if level:
            flush()
            path_stack[:] = path_stack[: max(0, level - 1)]
            path_stack.append(text)
        else:
            buf.append(text)
    flush()
    return title, sections


def _pdf_pages_text(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = [(p.extract_text() or "") for p in reader.pages]
    if sum(len(p.strip()) for p in pages) < 40 * max(1, len(pages)):
        # Scanned SOP: fall back to OCR.
        from .ocr import ocr_pdf
        pages = ocr_pdf(path)
    title = ""
    try:
        title = (reader.metadata.title or "").strip() if reader.metadata else ""
    except Exception:  # noqa: BLE001
        pass
    return title, pages


def parse_pdf(path):
    title, pages = _pdf_pages_text(path)
    sections, path_stack, buf = [], [], []

    def flush():
        text = "\n".join(buf).strip()
        if text:
            sections.append((" › ".join(path_stack) or "Introduction", text))
        buf.clear()

    for page in pages:
        for raw in page.splitlines():
            line = raw.strip()
            if not line or re.fullmatch(r"(page\s*)?\d+(\s*(of|/)\s*\d+)?", line, re.I):
                continue
            if _is_heading_line(line):
                if not title and not sections and not buf and not path_stack:
                    title = line.title() if line.isupper() else line
                    continue
                flush()
                m = HEADING_RE.match(line)
                level = m.group(1).count(".") + 1 if m else 1
                path_stack[:] = path_stack[: max(0, level - 1)]
                path_stack.append(line)
            else:
                buf.append(line)
    flush()
    return title, sections


def split_long(section_text, max_chars=1400):
    if len(section_text) <= max_chars:
        return [section_text]
    parts, cur = [], ""
    for para in section_text.split("\n"):
        if len(cur) + len(para) > max_chars and cur:
            parts.append(cur.strip())
            cur = cur[-200:]  # small overlap for continuity
        cur += "\n" + para
    if cur.strip():
        parts.append(cur.strip())
    return parts


def ingest_file(path, filename, user_id):
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".docx":
        title, sections = parse_docx(path)
    elif ext == ".pdf":
        title, sections = parse_pdf(path)
    else:
        raise HTTPException(400, "Please upload a PDF or Word (.docx) file")
    if not sections:
        raise HTTPException(400, "No readable text was found in this file")
    title = title or os.path.splitext(filename)[0].replace("_", " ")
    with tx():
        old = q1("SELECT id FROM sop_docs WHERE filename=?", (filename,))
        if old:  # re-upload replaces the previous version
            ex("DELETE FROM sop_chunks WHERE doc_id=?", (old["id"],))
            ex("DELETE FROM sop_docs WHERE id=?", (old["id"],))
        doc_id = ex("INSERT INTO sop_docs(filename, title, uploaded_by, uploaded_at, n_sections, stored_path) VALUES (?,?,?,?,?,?)",
                    (filename, title, user_id, now_s(), len(sections), path))
        o = 0
        for sec, text in sections:
            for piece in split_long(text):
                ex("INSERT INTO sop_chunks(doc_id, section, text, ord) VALUES (?,?,?,?)", (doc_id, sec, piece, o))
                o += 1
    INDEX.rebuild()
    return doc_id, title, len(sections)


# ---------------------------------------------------------------- retrieval

def normalize(text: str) -> str:
    t = text.lower()
    t = re.sub(r"(?<=\d),(?=\d)", "", t)                      # 10,000 -> 10000
    t = re.sub(r"₹|\brs\.?(?=\s*\d)|\binr\b", " rupees ", t)
    t = re.sub(r"\be-?mail\b", "email", t)
    return t


def extract_codes(qn: str) -> set:
    """Error codes and form references in a (normalised) question: 'error 402', 'code e-311', 'form dp-07'.
    Plain amounts like 10000 are not codes."""
    codes = set(re.findall(r"\b(?:error|err|code)\s*(?:no\.?|number|#)?\s*([a-z]{0,2}-?\d{2,4})\b", qn))
    codes |= set(re.findall(r"\b([a-z]{1,4}-\d{2,4})\b", qn))
    return codes


class SopIndex:
    def __init__(self):
        self.lock = threading.Lock()
        self.chunks = []
        self.word = self.char = self.title = None
        self.Xw = self.Xc = self.Xt = None

    def rebuild(self):
        with self.lock:
            self.chunks = q("""SELECT c.id, c.section, c.text, c.doc_id, d.title AS doc_title, d.filename
                               FROM sop_chunks c JOIN sop_docs d ON d.id=c.doc_id ORDER BY c.doc_id, c.ord""")
            if not self.chunks:
                self.word = self.char = self.title = None
                return
            corpus = [normalize(f"{c['doc_title']}. {c['section']}. {c['section']}. {c['text']}") for c in self.chunks]
            # Headings are a separate, short field. A long body dilutes its own heading,
            # so "which form for a duplicate payment" used to score a tie between
            # "4. Duplicate payments" and "Error 409 - Duplicate record". The heading
            # field is what breaks that tie correctly.
            headings = [normalize(f"{c['doc_title']} {c['section']}") for c in self.chunks]
            self.word = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english",
                                        token_pattern=r"(?u)\b\w+\b")
            self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
            self.title = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english",
                                         token_pattern=r"(?u)\b\w+\b")
            self.Xw = self.word.fit_transform(corpus)
            self.Xc = self.char.fit_transform(corpus)
            self.Xt = self.title.fit_transform(headings)

    def search(self, question: str, k=4):
        with self.lock:
            if self.word is None:
                return [], set()
            qn = normalize(question)
            sw = (self.Xw @ self.word.transform([qn]).T).toarray().ravel()
            sc = (self.Xc @ self.char.transform([qn]).T).toarray().ravel()
            st = (self.Xt @ self.title.transform([qn]).T).toarray().ravel()
            score = 0.55 * sw + 0.25 * sc + 0.20 * st
            # Exact codes/numbers in the question (error 402, form PR-07) are strong signals.
            codes = extract_codes(qn)
            if codes:
                for i, c in enumerate(self.chunks):
                    body = normalize(c["section"] + " " + c["text"])
                    if any(re.search(rf"\b{re.escape(code)}\b", body) for code in codes):
                        score[i] += 0.25
            order = np.argsort(-score)[:k]
            return [dict(self.chunks[i], score=float(score[i])) for i in order if score[i] > 0], codes


INDEX = SopIndex()

# ---------------------------------------------------------------- language


def detect_language(text: str) -> str:
    deva = sum("ऀ" <= ch <= "ॿ" for ch in text)
    guj = sum("઀" <= ch <= "૿" for ch in text)
    if guj > 2 and guj >= deva:
        return "gu"
    if deva > 2:
        return "hi"
    return "en"


LANG_NAMES = {"en": "English", "hi": "Hindi", "gu": "Gujarati"}


TRANSLATE_PROMPT = """Translate the user's question from Hindi or Gujarati into plain English.
Keep every number, code, amount and form name exactly as written. Output only the English question.
Examples:
त्रुटि 503 आने पर क्या करें? -> What should I do when error 503 appears?
ઓવરટાઇમ માટે કોની મંજૂરી જોઈએ? -> Whose approval is needed for overtime?
₹5,000 का रिफंड कौन मंजूर करता है? -> Who approves a refund of ₹5,000?"""


def to_english(question: str, lang: str) -> str:
    out = llm.chat(TRANSLATE_PROMPT, question, temperature=0.0, max_tokens=120).strip().strip('"')
    out = out.splitlines()[0].split("->")[-1].strip() if out else out
    # Numbers and codes must survive translation: re-attach any the model dropped.
    missing = [n for n in re.findall(r"[\d,]{2,}", question) if n.replace(",", "") not in out.replace(",", "")]
    return (out + " " + " ".join(missing)).strip()


# ---------------------------------------------------------------- answering

SYSTEM_PROMPT = """You answer questions from back-office staff using ONLY the SOP excerpts you are given.
Return JSON: {"found": true|false, "answer": "...", "sources": [excerpt numbers used]}
- found=true only if the excerpts state the answer. Then "answer" is 1-3 short sentences or numbered steps that
  directly answer the question, copying codes, amounts, form names, times and role titles exactly as written.
- found=false if the excerpts do not contain the answer. Never use outside knowledge and never guess."""

STRONG_MATCH = float(os.environ.get("SOP_STRONG_MATCH", "0.33"))


def _context_block(hits):
    return "\n\n".join(f"[{i}] Document: {h['doc_title']} | Section: {h['section']}\n{h['text']}"
                       for i, h in enumerate(hits, 1))


def _src(h, ref):
    return {"doc": h["doc_title"], "section": h["section"], "file": h["filename"], "excerpt": h["text"][:600], "ref": ref}


def _translate_answer(text, lang):
    return llm.chat(f"Translate the text into simple {LANG_NAMES[lang]}. Keep codes, numbers, amounts, form names and "
                    "role titles exactly as written (in Latin script). Output only the translation.",
                    text, temperature=0.0, max_tokens=400)


def _extractive(base, use, lang, note=""):
    h = use[0]
    text = h["text"] if len(h["text"]) < 900 else h["text"][:900].rsplit(" ", 1)[0] + " …"
    return dict(base, answer=f"{note}From the SOP — {h['section']}:\n{text}", status="answered", mode="extractive",
                sources=[_src(h, 1)])


def answer_question(question: str):
    """Returns dict(answer, sources, status, top_score, mode, language, english)."""
    lang = detect_language(question)
    st = llm.status()
    english = question

    if lang != "en":
        # Two routes to English: the deterministic lexicon always works, the model
        # translates better when it is running. Whichever retrieves a better section
        # wins, so the assistant never stalls just because no model is installed.
        variants = [("lexicon", lexicon.lexicon_to_english(question))]
        if st["online"]:
            try:
                model_version = to_english(question, lang)
                if model_version and model_version.strip():
                    variants.insert(0, ("model", model_version))
            except Exception:  # noqa: BLE001 - fall back to the lexicon
                pass
        best = None
        for how, eng in variants:
            h, c = INDEX.search(eng)
            s = h[0]["score"] if h else 0.0
            if best is None or s > best[0]:
                best = (s, how, eng, h, c)
        _, translated_by, english, hits, codes = best
    else:
        translated_by = None
        hits, codes = INDEX.search(english)

    top = hits[0]["score"] if hits else 0.0
    base = dict(language=lang, english=english, top_score=round(top, 3))
    if lang != "en":
        base["translated_by"] = translated_by
        base["understood"] = lexicon.mapped_terms(question) if translated_by == "lexicon" else []
        base["coverage"] = lexicon.coverage(question)

    # Gate: weak match, or an error code / form number that the best section does not mention.
    code_missing = bool(codes) and bool(hits) and not any(
        re.search(rf"\b{re.escape(c)}\b", normalize(hits[0]["section"] + " " + hits[0]["text"])) for c in codes)
    if not hits or top < MIN_SCORE or code_missing:
        return dict(base, answer=None, sources=[], status="needs_lead", mode="gate",
                    reason=("No SOP mentions " + ", ".join(sorted(codes)).upper() + ".") if code_missing
                    else "No SOP section matches this question closely enough.")

    use = [h for h in hits if h["score"] >= max(MIN_SCORE, 0.6 * top)][:3]
    if not st["online"]:
        return _extractive(base, use, lang,
                           note="The SOPs are in English, so the matching section is quoted as written.\n"
                           if lang != "en" else "")
    prompt = f"SOP excerpts:\n\n{_context_block(use)}\n\nQuestion: {english}"
    try:
        raw = llm.chat(SYSTEM_PROMPT, prompt, json_mode=True)
        data = json.loads(raw)
    except Exception:  # noqa: BLE001 - model offline / bad JSON: still help the user
        return _extractive(base, use, lang)
    answer = str(data.get("answer") or "").strip()
    found = bool(data.get("found")) and len(re.sub(r"\[\d+\]", "", answer).strip()) > 8
    if not found:
        if top >= STRONG_MATCH:
            # Very strong retrieval match but the model hesitated: show the section itself rather than nothing.
            return _extractive(base, use, lang)
        return dict(base, answer=None, sources=[], status="needs_lead", mode="llm",
                    reason="The SOPs do not contain this answer.")
    refs = []
    for n in data.get("sources") or []:
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if 0 < n <= len(use) and n not in refs:
            refs.append(n)
    refs = refs or [1]
    answer = re.sub(r"\s*\[\d+\]", "", answer).strip()
    answer_en = answer
    if lang != "en":
        try:
            answer = _translate_answer(answer, lang)
        except Exception:  # noqa: BLE001
            pass
    return dict(base, answer=answer, answer_en=answer_en, status="answered", mode="llm",
                sources=[_src(use[n - 1], n) for n in refs])


# ---------------------------------------------------------------- API

@router.get("/status")
def ai_status(user=Depends(current_user)):
    st = llm.status(force=True)
    n = q1("SELECT COUNT(*) AS n FROM sop_docs")["n"]
    return {**st, "documents": n}


@router.get("/docs")
def list_docs(user=Depends(current_user)):
    return {"docs": q("""SELECT d.id, d.filename, d.title, d.uploaded_at, d.n_sections, u.name AS uploaded_by
                         FROM sop_docs d LEFT JOIN users u ON u.id=d.uploaded_by ORDER BY d.title""")}


@router.post("/eval")
def run_eval(user=Depends(require("lead", "admin"))):
    """Run the SOP test questions here, scored exactly as scripts/eval_sop.py scores them.

    Imported lazily: app.evaluate imports this module, so a top-level import would be circular.
    """
    from .evaluate import run as run_questions
    return run_questions()


@router.post("/docs")
async def upload_doc(file: UploadFile = File(...), user=Depends(require("lead", "admin"))):
    name = os.path.basename(file.filename or "document")
    if os.path.splitext(name)[1].lower() not in (".pdf", ".docx"):
        raise HTTPException(400, "Please upload a PDF or Word (.docx) file")
    os.makedirs(SOP_DIR, exist_ok=True)
    path = os.path.join(SOP_DIR, f"{uuid.uuid4().hex}_{name}")
    # Read with a cap so a 4 GB upload is rejected instead of being loaded into memory.
    limit = 25 * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(400, "File is larger than 25 MB")
    # Writing a file is blocking work; keep it off the event loop.
    await asyncio.to_thread(Path(path).write_bytes, data)
    try:
        doc_id, title, n = ingest_file(path, name, user["id"])
    except HTTPException:
        os.remove(path)
        raise
    return {"id": doc_id, "title": title, "sections": n}


@router.get("/docs/{doc_id}/sections")
def doc_sections(doc_id: int, user=Depends(current_user)):
    d = q1("SELECT id, title, filename FROM sop_docs WHERE id=?", (doc_id,))
    if not d:
        raise HTTPException(404, "Document not found")
    return {"doc": d, "sections": q("SELECT section, text FROM sop_chunks WHERE doc_id=? ORDER BY ord", (doc_id,))}


@router.delete("/docs/{doc_id}")
def delete_doc(doc_id: int, user=Depends(require("lead", "admin"))):
    d = q1("SELECT * FROM sop_docs WHERE id=?", (doc_id,))
    if not d:
        raise HTTPException(404, "Document not found")
    with tx():
        ex("DELETE FROM sop_chunks WHERE doc_id=?", (doc_id,))
        ex("DELETE FROM sop_docs WHERE id=?", (doc_id,))
    try:
        os.remove(d["stored_path"])
    except OSError:
        pass
    INDEX.rebuild()
    return {"ok": True}


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=600)


@router.post("/ask")
def ask(body: AskIn, user=Depends(current_user)):
    res = answer_question(body.question.strip())
    qid = ex("""INSERT INTO questions(user_id, asked_at, question, language, answer, sources, status, top_score, mode)
                VALUES (?,?,?,?,?,?,?,?,?)""",
             (user["id"], now_s(), body.question.strip(), res["language"], res.get("answer"),
              json.dumps(res.get("sources", [])), res["status"], res["top_score"], res["mode"]))
    if res["status"] == "needs_lead":
        for lead in q("SELECT id FROM users WHERE role='lead' AND active=1"):
            notify(lead["id"], f"Question needs you: “{body.question.strip()[:80]}” — {user['name']}", "#/needs-lead")
    return {"id": qid, **res}


@router.get("/my-questions")
def my_questions(user=Depends(current_user)):
    rows = q("SELECT * FROM questions WHERE user_id=? ORDER BY id DESC LIMIT 30", (user["id"],))
    for r in rows:
        r["sources"] = json.loads(r["sources"] or "[]")
    return {"questions": rows}


@router.get("/questions")
def all_questions(status: str | None = "needs_lead", user=Depends(require("lead", "admin"))):
    sql = """SELECT qu.*, u.name AS asked_by, r.name AS resolved_by_name FROM questions qu
             LEFT JOIN users u ON u.id=qu.user_id LEFT JOIN users r ON r.id=qu.resolved_by"""
    params = ()
    if status and status != "all":
        sql += " WHERE qu.status=?"; params = (status,)
    rows = q(sql + " ORDER BY qu.id DESC LIMIT 300", params)
    for r in rows:
        r["sources"] = json.loads(r["sources"] or "[]")
    counts = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) AS n FROM questions GROUP BY status")}
    return {"questions": rows, "counts": counts}


class ResolveIn(BaseModel):
    answer: str = Field(min_length=2, max_length=4000)
@router.post("/questions/{qid}/resolve")
def resolve(qid: int, body: ResolveIn, user=Depends(require("lead", "admin"))):
    qu = q1("SELECT * FROM questions WHERE id=?", (qid,))
    if not qu:
        raise HTTPException(404, "Question not found")
    ex("UPDATE questions SET status='resolved', lead_answer=?, resolved_by=?, resolved_at=? WHERE id=?",
       (body.answer.strip(), user["id"], now_s(), qid))
    if qu["user_id"]:
        notify(qu["user_id"], f"{user['name']} answered your question: “{qu['question'][:70]}”", "#/assistant")
    return {"ok": True}


class FeedbackIn(BaseModel):
    helpful: bool


@router.post("/questions/{qid}/feedback")
def answer_feedback(qid: int, body: FeedbackIn, user=Depends(current_user)):
    qu = q1("SELECT * FROM questions WHERE id=? AND user_id=?", (qid, user["id"]))
    if not qu:
        raise HTTPException(404, "Question not found")
    ex("UPDATE questions SET helpful=? WHERE id=?", (1 if body.helpful else 0, qid))
    if not body.helpful and qu["status"] == "answered":
        ex("UPDATE questions SET status='needs_lead' WHERE id=?", (qid,))
        for lead in q("SELECT id FROM users WHERE role='lead' AND active=1"):
            notify(lead["id"], f"Answer marked unhelpful: “{qu['question'][:80]}”", "#/needs-lead")
    return {"ok": True}
