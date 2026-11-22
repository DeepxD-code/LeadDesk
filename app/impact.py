"""Impact numbers, computed from the live database.

Judges are told the same thing at every hackathon dry run: "you are missing numbers".
These are not marketing figures - every one is a COUNT over the demo data, and every
assumption is named in the `assumptions` list so nobody has to take it on trust.
"""
import os
from datetime import timedelta

from .db import now, q, q1

WINDOW_DAYS = int(os.environ.get("IMPACT_WINDOW_DAYS", "7"))
# Minutes a lead loses per interruption: find the SOP, read it, answer, get back
# to what they were doing. Deliberately conservative; the brief describes minutes
# per question adding up to hours.
MINUTES_PER_QUESTION = float(os.environ.get("ASSUMED_MINUTES_PER_QUESTION", "4"))


def compute() -> dict:
    since = (now() - timedelta(days=WINDOW_DAYS)).isoformat(timespec="seconds")
    today = now().date().isoformat()
    now_s = now().isoformat(timespec="seconds")

    # ---------- the assistant
    counts = {r["status"]: r["n"] for r in q(
        "SELECT status, COUNT(*) AS n FROM questions WHERE asked_at >= ? GROUP BY status", (since,))}
    asked = sum(counts.values())
    answered = counts.get("answered", 0) + counts.get("resolved", 0)
    needs_lead = counts.get("needs_lead", 0)
    answer_rate = round(100 * answered / asked) if asked else 0
    hours_saved = round(answered * MINUTES_PER_QUESTION / 60, 1)

    # ---------- the task board
    open_states = ("pending", "in_progress", "escalated")
    tasks_total = q1("SELECT COUNT(*) AS n FROM tasks")["n"]
    overdue = q1("""SELECT COUNT(*) AS n FROM tasks
                    WHERE status IN (?,?,?) AND deadline < ?""", (*open_states, now_s))["n"]
    due_today = q1("""SELECT COUNT(*) AS n FROM tasks
                      WHERE status IN (?,?,?) AND deadline >= ? AND deadline < ?""",
                   (*open_states, f"{today}T00:00", f"{today}T23:59"))["n"]
    members = q1("SELECT COUNT(*) AS n FROM users WHERE role='member' AND active=1")["n"]

    threshold = float(q1("SELECT value FROM settings WHERE key='overload_threshold'")["value"])
    per_member = q("""SELECT u.id, u.name, COUNT(t.id) AS open FROM users u
                      LEFT JOIN tasks t ON t.assignee_id=u.id AND t.status IN (?,?,?)
                      WHERE u.role='member' AND u.active=1 GROUP BY u.id""", open_states)
    overloaded = [m for m in per_member if m["open"] > threshold]
    busiest = max(per_member, key=lambda m: m["open"]) if per_member else None

    # ---------- the vault
    vault_docs = q1("SELECT COUNT(*) AS n FROM vault_docs WHERE deleted=0")["n"]
    vault_scans = q1("SELECT COUNT(*) AS n FROM vault_docs WHERE deleted=0 AND ocr_used=1")["n"]
    audit_entries = q1("SELECT COUNT(*) AS n FROM audit_log")["n"]

    # ---------- interviews
    scheduled = q1("SELECT COUNT(*) AS n FROM interviews WHERE status='scheduled' AND start > ?", (now_s,))["n"]
    interview_minutes = q1("""SELECT COALESCE(SUM(COALESCE(i.length_min, s.length_min)), 0) AS n
                              FROM interviews i LEFT JOIN slots s ON s.id=i.slot_id
                              WHERE i.status='scheduled' AND i.start > ?""", (now_s,))["n"]
    feedback_pending = q1("""SELECT COUNT(*) AS n FROM interviews i
                             WHERE i.status='scheduled' AND i.end < ?
                               AND NOT EXISTS (SELECT 1 FROM feedback f
                                               WHERE f.interview_id=i.id AND f.interviewer_id=i.interviewer_id)""",
                          (now_s,))["n"]

    return {
        "window_days": WINDOW_DAYS,
        "assistant": {
            "asked": asked, "answered": answered, "needs_lead": needs_lead,
            "answer_rate_pct": answer_rate, "hours_saved": hours_saved,
            "answered_per_day": round(answered / WINDOW_DAYS, 1),
        },
        "board": {
            "tasks": tasks_total, "overdue": overdue, "due_today": due_today,
            "members": members, "overloaded": len(overloaded),
            "busiest": busiest, "threshold": threshold,
        },
        "vault": {"documents": vault_docs, "scans_searchable": vault_scans, "audit_entries": audit_entries},
        "interviews": {"upcoming": scheduled, "hours_booked": round(interview_minutes / 60, 1),
                       "feedback_pending": feedback_pending},
        "assumptions": [
            f"A lead loses {MINUTES_PER_QUESTION:g} minutes per question answered from the SOPs "
            "(find the section, read it, answer, resume).",
            f"Window is the last {WINDOW_DAYS} days of this demo data.",
            "Hours saved counts questions the assistant answered, not the ones it escalated to a lead.",
            "A question sent to the lead is a gap in the SOPs, not a failure - it is listed for fixing.",
        ],
    }
