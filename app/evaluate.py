"""Runs the SOP test questions and scores them. Used by scripts/eval_sop.py and the in-app 'Run test' button."""
import json
import os
import time

from . import llm, sop
from .db import DATA_DIR, now_s

QUESTIONS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_data", "test_questions.json")
RESULTS = os.path.join(DATA_DIR, "eval_results.json")


def run(path=QUESTIONS):
    with open(path, encoding="utf-8") as f:
        tests = json.load(f)
    rows = []
    for t in tests:
        s = time.time()
        r = sop.answer_question(t["q"])
        ok_status = r["status"] == t["expect"] or (t["expect"] == "answer" and r["status"] == "answered")
        text = (r.get("answer") or "")
        hay = text + " " + " ".join(x["section"] + " " + x["excerpt"] for x in r.get("sources", []))
        ok_content = all(m.lower() in hay.lower() for m in t.get("must", []))
        ok_source = not t.get("source") or any(t["source"].lower() in x["doc"].lower() for x in r.get("sources", []))
        passed = ok_status and (t["expect"] != "answer" or (ok_content and ok_source))
        rows.append({"question": t["q"], "expected": t["expect"], "got": r["status"], "mode": r["mode"],
                     "answer": r.get("answer") or r.get("reason"), "sources": [f"{x['doc']} › {x['section']}" for x in r.get("sources", [])],
                     "score": r["top_score"], "passed": passed, "lang": t.get("lang", "en"), "seconds": round(time.time() - s, 1)})
    core = [r for r in rows if r["lang"] == "en"]
    out = {
        "at": now_s(), "model": llm.LLM_MODEL, "ai_online": llm.status()["online"],
        "answerable_passed": sum(r["passed"] for r in core if r["expected"] == "answer"),
        "answerable_total": sum(r["expected"] == "answer" for r in core),
        "gaps_caught": sum(r["passed"] for r in core if r["expected"] == "needs_lead"),
        "gaps_total": sum(r["expected"] == "needs_lead" for r in core),
        "multilingual_passed": sum(r["passed"] for r in rows if r["lang"] != "en"),
        "multilingual_total": sum(r["lang"] != "en" for r in rows),
        "rows": rows,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out
