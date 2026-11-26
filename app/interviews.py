"""Interview scheduler: availability, self-service booking links, .ics invites, reminders, structured feedback."""
import io
import json
import os
import re
import secrets
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from . import google_calendar, mailer
from .auth import current_user, require
from .db import TZ_NAME, ex, notify, now, now_s, q, q1, tx
from .ics import build_ics

router = APIRouter(prefix="/api/iv", tags=["interviews"])
public = APIRouter(prefix="/api/book", tags=["booking"])

BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
ORGANIZER = os.environ.get("ORGANIZER_EMAIL", "scheduler@leaddesk.local")
LENGTHS = (30, 45, 60)
CRITERIA = ["communication", "technical", "problem_solving", "culture_fit"]
MIN_NOTICE_MIN = int(os.environ.get("BOOKING_MIN_NOTICE_MIN", "60"))
IST = timezone(timedelta(hours=5, minutes=30))

# ------------------------------------------------------------------ helpers


def _dt(s):
    return datetime.fromisoformat(s)


def _fmt(s):
    return _dt(s).strftime("%a %d %b %Y, %I:%M %p") + " IST"


def link_for(token):
    return f"{BASE_URL}/book/{token}"


IV_SELECT = """SELECT i.*, c.name AS candidate_name, c.email AS candidate_email, c.role_title, c.recruiter_id,
               r.name AS recruiter_name, u.name AS interviewer_name, u.email AS interviewer_email
               FROM interviews i JOIN candidates c ON c.id=i.candidate_id
               LEFT JOIN users r ON r.id=c.recruiter_id LEFT JOIN users u ON u.id=i.interviewer_id"""


def board_status(iv, fb_ids=None):
    if iv["status"] == "invited":
        return "invited"
    if iv["status"] == "cancelled":
        return "cancelled"
    if _dt(iv["end"]) > now():
        return "rescheduled" if iv["reschedule_count"] else "scheduled"
    has_fb = iv["id"] in fb_ids if fb_ids is not None else bool(
        q1("SELECT 1 FROM feedback WHERE interview_id=? AND interviewer_id=?", (iv["id"], iv["interviewer_id"])))
    return "completed" if has_fb else "feedback_pending"


def _ics_for(iv, cancel=False, for_interviewer_id=None):
    inter = q1("SELECT * FROM users WHERE id=?", (for_interviewer_id or iv["interviewer_id"],))
    summary = f"{iv['round_name']}: {iv['candidate_name']} — {iv['role_title']}"
    desc = (f"Interview for {iv['role_title']}.\nCandidate: {iv['candidate_name']}\nInterviewer: {inter['name']}\n"
            f"Join / location: {iv['location']}\nReschedule or cancel: {link_for(iv['token'])}\nTime zone: {TZ_NAME}")
    return build_ics(f"interview-{iv['id']}@leaddesk.local", _dt(iv["start"]), _dt(iv["end"]), summary, desc,
                     iv["location"], ORGANIZER, [(iv["candidate_name"], iv["candidate_email"]), (inter["name"], inter["email"])],
                     sequence=iv["ics_sequence"], cancel=cancel)


def _send_invites(iv, kind, old_interviewer_id=None):
    """kind: booked | rescheduled | cancelled"""
    when = _fmt(iv["start"])
    cancel = kind == "cancelled"
    ics = _ics_for(iv, cancel=cancel)
    method = "CANCEL" if cancel else "REQUEST"
    subj = {"booked": "Interview confirmed", "rescheduled": "Interview rescheduled",
            "cancelled": "Interview cancelled"}[kind]
    cand_body = (f"Hello {iv['candidate_name']},\n\nYour {iv['round_name'].lower()} for {iv['role_title']} is "
                 f"{'cancelled' if cancel else 'confirmed for ' + when}.\n"
                 + ("" if cancel else f"Join / location: {iv['location']}\nInterviewer: {iv['interviewer_name']}\n")
                 + f"\nNeed to change it? {link_for(iv['token'])}\n\nThe attached invite.ics adds it to your calendar.\n")
    mailer.send(iv["candidate_email"], f"{subj}: {iv['role_title']} — {when}", cand_body, ics, method, kind)
    int_body = (f"Hello {iv['interviewer_name']},\n\n{iv['candidate_name']} ({iv['role_title']}) "
                f"{'cancelled' if cancel else 'is booked for ' + when}.\nLocation: {iv['location']}\n")
    mailer.send(iv["interviewer_email"], f"{subj}: {iv['candidate_name']} — {when}", int_body, ics, method, kind)
    notify(iv["interviewer_id"], f"{subj}: {iv['candidate_name']} ({iv['role_title']}) — {when}", "#/interviews")
    if old_interviewer_id and old_interviewer_id != iv["interviewer_id"]:
        old = q1("SELECT * FROM users WHERE id=?", (old_interviewer_id,))
        mailer.send(old["email"], f"Interview moved away: {iv['candidate_name']}", "This interview was moved to a colleague.",
                    _ics_for(iv, cancel=True, for_interviewer_id=old_interviewer_id), "CANCEL", "cancelled")
        notify(old_interviewer_id, f"Interview moved to another interviewer: {iv['candidate_name']}", "#/interviews")


def open_slots(length_min=None, exclude_interview_id=0, slot_id=None):
    earliest = (now() + timedelta(minutes=MIN_NOTICE_MIN)).isoformat(timespec="minutes")
    sql = """SELECT s.*, u.name AS interviewer_name FROM slots s JOIN users u ON u.id=s.interviewer_id
             WHERE s.status='open' AND s.start >= ?
               AND NOT EXISTS (SELECT 1 FROM interviews i WHERE i.status='scheduled' AND i.id != ?
                               AND i.interviewer_id=s.interviewer_id AND i.start < s.end AND i.end > s.start)"""
    params = [earliest, exclude_interview_id]
    if length_min:
        sql += " AND s.length_min=?"; params.append(length_min)
    if slot_id:
        sql += " AND s.id=?"; params.append(slot_id)
    return q(sql + " ORDER BY s.start, u.name", params)


def _calendar_free_slots(slots):
    by_interviewer = {}
    for slot in slots:
        by_interviewer.setdefault(slot["interviewer_id"], []).append(slot)
    available = []
    for interviewer_id, rows in by_interviewer.items():
        try:
            busy = google_calendar.busy_intervals(
                interviewer_id,
                min(row["start"] for row in rows),
                max(row["end"] for row in rows),
            )
        except google_calendar.GoogleCalendarError as exc:
            raise HTTPException(503, f"Could not check Google Calendar availability: {exc}") from exc
        if busy is None:
            available.extend(rows)
            continue
        for row in rows:
            start = _dt(row["start"]).replace(tzinfo=IST)
            end = _dt(row["end"]).replace(tzinfo=IST)
            if not any(start < busy_end and end > busy_start for busy_start, busy_end in busy):
                available.append(row)
    return available


def _check_calendar_slot(slot):
    try:
        busy = google_calendar.busy_intervals(slot["interviewer_id"], slot["start"], slot["end"])
    except google_calendar.GoogleCalendarError as exc:
        raise HTTPException(503, f"Could not check Google Calendar availability: {exc}") from exc
    if busy is None:
        return
    start = _dt(slot["start"]).replace(tzinfo=IST)
    end = _dt(slot["end"]).replace(tzinfo=IST)
    if any(start < busy_end and end > busy_start for busy_start, busy_end in busy):
        raise HTTPException(409, "That time is busy on the interviewer's Google Calendar. Choose another slot.")


# ------------------------------------------------------------------ interviewer: availability

class SlotIn(BaseModel):
    day: str                      # YYYY-MM-DD
    start_time: str               # HH:MM
    end_time: str                 # HH:MM
    length_min: int = 30
    repeat_weeks: int = Field(0, ge=0, le=12)   # 0 = one-off; N = also the same weekday for N more weeks
    location: str = ""
    interviewer_id: int | None = None           # recruiters/admin may add slots for an interviewer


class MeetingIn(BaseModel):
    summary: str = Field(min_length=1, max_length=200)
    start: str                    # YYYY-MM-DDTHH:MM in IST
    end: str                      # YYYY-MM-DDTHH:MM in IST
    attendees: str = ""           # comma/space separated emails
    description: str = Field("", max_length=2000)
    location: str = Field("", max_length=300)
    calendar_id: str = Field("primary", max_length=300)
    meet: bool = False            # ask Google to attach a Meet link


@router.get("/slots")
def my_slots(interviewer_id: int | None = None, user=Depends(current_user)):
    iid = interviewer_id if (interviewer_id and user["role"] in ("hr", "admin")) else user["id"]
    rows = q("""SELECT s.*, (SELECT i.id FROM interviews i WHERE i.slot_id=s.id AND i.status='scheduled') AS interview_id,
                       (SELECT c.name FROM interviews i JOIN candidates c ON c.id=i.candidate_id
                        WHERE i.slot_id=s.id AND i.status='scheduled') AS candidate_name
                FROM slots s WHERE s.interviewer_id=? AND s.status='open' AND s.end >= ? ORDER BY s.start""",
             (iid, now().isoformat(timespec="minutes")))
    blocked = {s["id"] for s in rows} - {s["id"] for s in open_slots()}
    busy = None
    if rows and iid == user["id"]:
        try:
            busy = google_calendar.busy_intervals(iid, min(s["start"] for s in rows), max(s["end"] for s in rows))
        except google_calendar.GoogleCalendarError as exc:
            raise HTTPException(503, f"Could not check Google Calendar availability: {exc}") from exc
    for s in rows:
        start = _dt(s["start"]).replace(tzinfo=IST)
        end = _dt(s["end"]).replace(tzinfo=IST)
        calendar_blocked = busy is not None and any(start < b_end and end > b_start for b_start, b_end in busy)
        s["state"] = ("booked" if s["interview_id"] else
                      "blocked" if s["id"] in blocked else
                      "calendar_blocked" if calendar_blocked else "open")
    return {"slots": rows, "lengths": LENGTHS, "time_zone": TZ_NAME,
            "google_calendar": google_calendar.status(user["id"]) if user["role"] == "interviewer" else None}


@router.get("/google/status")
def google_status(user=Depends(require("interviewer"))):
    return google_calendar.status(user["id"])


@router.get("/google/connect")
def google_connect(user=Depends(require("interviewer"))):
    try:
        url = google_calendar.authorization_url(user["id"])
    except google_calendar.GoogleCalendarError as exc:
        raise HTTPException(503, str(exc)) from exc
    return RedirectResponse(url, status_code=302)


@router.get("/google/callback")
def google_callback(state: str = "", code: str | None = None, error: str | None = None,
                    user=Depends(require("interviewer"))):
    if error:
        raise HTTPException(400, f"Google authorization was not completed: {error}")
    try:
        google_calendar.complete_authorization(user["id"], state, code or "")
    except google_calendar.GoogleCalendarError as exc:
        raise HTTPException(502, str(exc)) from exc
    return RedirectResponse(f"{BASE_URL}/#/availability?google=connected", status_code=303)


@router.post("/google/disconnect")
def google_disconnect(user=Depends(require("interviewer"))):
    try:
        return google_calendar.disconnect(user["id"])
    except google_calendar.GoogleCalendarError as exc:
        raise HTTPException(502, str(exc)) from exc


def _meeting_fields(body: MeetingIn):
    """Validate a meeting form once, for both create and edit."""
    summary = body.summary.strip()
    if not summary:
        raise HTTPException(400, "Give the meeting a title")
    try:
        start = datetime.fromisoformat(body.start)
        end = datetime.fromisoformat(body.end)
    except ValueError:
        raise HTTPException(400, "Use a valid date and HH:MM times")
    if end <= start:
        raise HTTPException(400, "End time must be after start time")
    if end - start > timedelta(hours=12):
        raise HTTPException(400, "A single meeting cannot be longer than 12 hours")
    emails = []
    for raw in re.split(r"[\s,;]+", body.attendees.strip()):
        if not raw:
            continue
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", raw):
            raise HTTPException(400, f"{raw} is not a valid email address")
        email = raw.lower()
        if email not in emails:
            emails.append(email)
    if len(emails) > 20:
        raise HTTPException(400, "Add at most 20 attendees")
    calendar_id = body.calendar_id.strip() or "primary"
    if not calendar_id or re.search(r"\s", calendar_id):
        raise HTTPException(400, "Choose a valid calendar")
    return summary, emails, calendar_id


def _meeting_public(row):
    meeting = dict(row)
    try:
        meeting["attendees"] = json.loads(meeting.get("attendees") or "[]")
    except (TypeError, ValueError):
        meeting["attendees"] = []
    return meeting


@router.get("/google/calendars")
def google_calendars(user=Depends(require("interviewer"))):
    if not google_calendar.has_connection(user["id"]):
        raise HTTPException(400, "Connect Google Calendar first")
    try:
        return {"calendars": google_calendar.list_calendars(user["id"])}
    except google_calendar.GoogleCalendarError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/google/meetings")
def google_meetings(user=Depends(require("interviewer"))):
    """Upcoming meetings created from LeadDesk, newest first."""
    rows = q("""SELECT * FROM google_meetings
                WHERE user_id=? AND status='active' AND end >= ?
                ORDER BY start LIMIT 50""",
             (user["id"], now().strftime("%Y-%m-%dT%H:%M")))
    return {"meetings": [_meeting_public(row) for row in rows]}


@router.post("/google/meeting")
def google_create_meeting(body: MeetingIn, user=Depends(require("interviewer"))):
    """Create a one-off meeting on a writable Google Calendar."""
    summary, emails, calendar_id = _meeting_fields(body)
    if not google_calendar.has_connection(user["id"]):
        raise HTTPException(400, "Connect Google Calendar before creating a meeting")
    try:
        result = google_calendar.create_meeting(
            user["id"], summary, body.start, body.end,
            description=body.description.strip(), location=body.location.strip(), attendees=emails,
            calendar_id=calendar_id, meet=body.meet,
        )
    except google_calendar.GoogleCalendarError as exc:
        raise HTTPException(502, str(exc)) from exc
    ts = now_s()
    meeting_id = ex("""INSERT INTO google_meetings(user_id, calendar_id, event_id, summary, start, end,
                       attendees, location, description, meet_link, html_link, status, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?, 'active', ?, ?)""",
                    (user["id"], calendar_id, result.get("id"), summary, body.start, body.end,
                     json.dumps(emails), body.location.strip(), body.description.strip(),
                     result.get("meet_link"), result.get("htmlLink"), ts, ts))
    return {**result, "meeting_id": meeting_id, "attendees": emails}


@router.patch("/google/meeting/{meeting_id}")
def google_update_meeting(meeting_id: int, body: MeetingIn, user=Depends(require("interviewer"))):
    """Edit a meeting created from LeadDesk. The event stays on its original calendar."""
    row = q1("SELECT * FROM google_meetings WHERE id=? AND user_id=?", (meeting_id, user["id"]))
    if not row:
        raise HTTPException(404, "Meeting not found")
    if row["status"] != "active":
        raise HTTPException(400, "This meeting was already cancelled")
    summary, emails, _ = _meeting_fields(body)
    if not google_calendar.has_connection(user["id"]):
        raise HTTPException(400, "Connect Google Calendar before editing a meeting")
    try:
        result = google_calendar.update_meeting(
            user["id"], row["calendar_id"], row["event_id"], summary, body.start, body.end,
            description=body.description.strip(), location=body.location.strip(), attendees=emails,
            meet=body.meet and not row["meet_link"],
        )
    except google_calendar.GoogleCalendarError as exc:
        raise HTTPException(502, str(exc)) from exc
    ex("""UPDATE google_meetings SET summary=?, start=?, end=?, attendees=?, location=?, description=?,
          meet_link=COALESCE(?, meet_link), html_link=COALESCE(?, html_link), updated_at=? WHERE id=?""",
       (summary, body.start, body.end, json.dumps(emails), body.location.strip(), body.description.strip(),
        result.get("meet_link"), result.get("htmlLink"), now_s(), meeting_id))
    return {**result, "meeting_id": meeting_id, "attendees": emails}


@router.delete("/google/meeting/{meeting_id}")
def google_cancel_meeting(meeting_id: int, user=Depends(require("interviewer"))):
    row = q1("SELECT * FROM google_meetings WHERE id=? AND user_id=?", (meeting_id, user["id"]))
    if not row:
        raise HTTPException(404, "Meeting not found")
    if row["status"] != "active":
        return {"ok": True, "already": True}
    try:
        result = google_calendar.delete_meeting(user["id"], row["calendar_id"], row["event_id"])
    except google_calendar.GoogleCalendarError as exc:
        raise HTTPException(502, str(exc)) from exc
    ex("UPDATE google_meetings SET status='cancelled', updated_at=? WHERE id=?", (now_s(), meeting_id))
    return {**result, "ok": True}


@router.post("/slots")
def add_slots(body: SlotIn, user=Depends(require("interviewer", "hr", "admin"))):
    iid = body.interviewer_id if (body.interviewer_id and user["role"] in ("hr", "admin")) else user["id"]
    if not q1("SELECT 1 FROM users WHERE id=? AND role='interviewer'", (iid,)):
        raise HTTPException(400, "Slots can only be added for interviewers")
    if body.length_min not in LENGTHS:
        raise HTTPException(400, "Interview length must be 30, 45 or 60 minutes")
    try:
        d0 = date.fromisoformat(body.day)
        t0 = datetime.strptime(body.start_time, "%H:%M").time()
        t1 = datetime.strptime(body.end_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(400, "Use a valid date and HH:MM times")
    if t1 <= t0:
        raise HTTPException(400, "End time must be after start time")
    series = uuid.uuid4().hex[:10] if body.repeat_weeks else None
    created = skipped = 0
    existing = q("SELECT start, end FROM slots WHERE interviewer_id=? AND status='open'", (iid,))
    with tx():
        for w in range(body.repeat_weeks + 1):
            d = d0 + timedelta(weeks=w)
            cur, end = datetime.combine(d, t0), datetime.combine(d, t1)
            while cur + timedelta(minutes=body.length_min) <= end:
                s, e = cur.isoformat(timespec="minutes"), (cur + timedelta(minutes=body.length_min)).isoformat(timespec="minutes")
                if cur <= now() or any(x["start"] < e and x["end"] > s for x in existing):
                    skipped += 1
                else:
                    ex("INSERT INTO slots(interviewer_id, start, end, length_min, series_id, location) VALUES (?,?,?,?,?,?)",
                       (iid, s, e, body.length_min, series, body.location.strip() or None))
                    existing.append({"start": s, "end": e})
                    created += 1
                cur += timedelta(minutes=body.length_min)
    return {"created": created, "skipped": skipped}


@router.delete("/slots/{slot_id}")
def remove_slot(slot_id: int, user=Depends(require("interviewer", "hr", "admin"))):
    s = q1("SELECT * FROM slots WHERE id=?", (slot_id,))
    if not s or (user["role"] == "interviewer" and s["interviewer_id"] != user["id"]):
        raise HTTPException(404, "Slot not found")
    if q1("SELECT 1 FROM interviews WHERE slot_id=? AND status='scheduled'", (slot_id,)):
        raise HTTPException(400, "This slot is booked. Ask the recruiter to cancel or the candidate to reschedule.")
    ex("UPDATE slots SET status='removed' WHERE id=?", (slot_id,))
    return {"ok": True}


# ------------------------------------------------------------------ interviewer: my interviews + feedback

@router.get("/mine")
def my_interviews(user=Depends(require("interviewer", "admin"))):
    rows = q(IV_SELECT + " WHERE i.interviewer_id=? AND i.status='scheduled' ORDER BY i.start", (user["id"],))
    fb = {r["interview_id"] for r in q("SELECT interview_id FROM feedback WHERE interviewer_id=?", (user["id"],))}
    for r in rows:
        r["board_status"] = board_status(r, fb)
        r["feedback_submitted"] = r["id"] in fb
    return {"interviews": rows}


class FeedbackIn(BaseModel):
    communication: int = Field(ge=1, le=5)
    technical: int = Field(ge=1, le=5)
    problem_solving: int = Field(ge=1, le=5)
    culture_fit: int = Field(ge=1, le=5)
    recommendation: str
    comments: str = ""


@router.post("/interviews/{iid}/feedback")
def submit_feedback(iid: int, body: FeedbackIn, user=Depends(require("interviewer"))):
    iv = q1("SELECT * FROM interviews WHERE id=? AND status='scheduled'", (iid,))
    if not iv or iv["interviewer_id"] != user["id"]:
        raise HTTPException(404, "Interview not found")
    if _dt(iv["start"]) > now():
        raise HTTPException(400, "Feedback opens once the interview has started")
    if body.recommendation not in ("advance", "hold", "reject"):
        raise HTTPException(400, "Recommendation must be advance, hold or reject")
    if q1("SELECT 1 FROM feedback WHERE interview_id=? AND interviewer_id=?", (iid, user["id"])):
        raise HTTPException(400, "Feedback already submitted")
    ex("""INSERT INTO feedback(interview_id, interviewer_id, communication, technical, problem_solving, culture_fit,
          recommendation, comments, submitted_at) VALUES (?,?,?,?,?,?,?,?,?)""",
       (iid, user["id"], body.communication, body.technical, body.problem_solving, body.culture_fit,
        body.recommendation, body.comments.strip(), now_s()))
    return {"ok": True}


class InterviewNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def require_note_text(cls, value):
        if not value.strip():
            raise ValueError("Note cannot be blank")
        return value.strip()


def _interview_for_notes(iid, user):
    interview = q1("SELECT * FROM interviews WHERE id=?", (iid,))
    if not interview:
        raise HTTPException(404, "Interview not found")
    if user["role"] == "hr":
        return interview
    if user["role"] == "interviewer" and interview["interviewer_id"] == user["id"]:
        return interview
    raise HTTPException(404, "Interview not found")


@router.get("/interviews/{iid}/notes")
def interview_notes(iid: int, user=Depends(current_user)):
    _interview_for_notes(iid, user)
    rows = q("""SELECT n.*, u.name AS author_name FROM interview_notes n
                JOIN users u ON u.id=n.author_id WHERE n.interview_id=?
                ORDER BY n.created_at DESC, n.id DESC""", (iid,))
    for row in rows:
        row["can_edit"] = row["author_id"] == user["id"]
    return {"notes": rows}


@router.post("/interviews/{iid}/notes", status_code=201)
def add_interview_note(iid: int, body: InterviewNoteIn, user=Depends(current_user)):
    _interview_for_notes(iid, user)
    ts = now_s()
    note_id = ex("""INSERT INTO interview_notes(interview_id, author_id, body, created_at, updated_at)
                    VALUES (?,?,?,?,?)""", (iid, user["id"], body.body, ts, ts))
    return {"note": {"id": note_id, "interview_id": iid, "author_id": user["id"], "author_name": user["name"],
                     "body": body.body, "created_at": ts, "updated_at": ts, "can_edit": True}}


@router.patch("/notes/{note_id}")
def update_interview_note(note_id: int, body: InterviewNoteIn, user=Depends(current_user)):
    note = q1("SELECT * FROM interview_notes WHERE id=?", (note_id,))
    if not note:
        raise HTTPException(404, "Note not found")
    _interview_for_notes(note["interview_id"], user)
    if note["author_id"] != user["id"]:
        raise HTTPException(403, "Only the note author can edit it")
    ex("UPDATE interview_notes SET body=?, updated_at=? WHERE id=?", (body.body, now_s(), note_id))
    return {"ok": True}


@router.delete("/notes/{note_id}")
def delete_interview_note(note_id: int, user=Depends(current_user)):
    note = q1("SELECT * FROM interview_notes WHERE id=?", (note_id,))
    if not note:
        raise HTTPException(404, "Note not found")
    _interview_for_notes(note["interview_id"], user)
    if note["author_id"] != user["id"]:
        raise HTTPException(403, "Only the note author can delete it")
    ex("DELETE FROM interview_notes WHERE id=?", (note_id,))
    return {"ok": True}


@router.get("/candidates/{cid}/feedback")
def candidate_feedback(cid: int, user=Depends(current_user)):
    """Independent feedback: an interviewer sees colleagues' feedback on a candidate only after submitting their own."""
    all_fb = q("""SELECT f.*, u.name AS interviewer_name, i.round_name, i.start FROM feedback f
                  JOIN interviews i ON i.id=f.interview_id JOIN users u ON u.id=f.interviewer_id
                  WHERE i.candidate_id=? ORDER BY f.submitted_at""", (cid,))
    if user["role"] in ("hr", "admin"):
        return {"feedback": all_fb, "hidden": 0, "locked": False}
    if user["role"] != "interviewer":
        raise HTTPException(403, "Not allowed")
    mine = [f for f in all_fb if f["interviewer_id"] == user["id"]]
    if not q1("SELECT 1 FROM interviews WHERE candidate_id=? AND interviewer_id=?", (cid, user["id"])):
        raise HTTPException(403, "You have not interviewed this candidate")
    if not mine:
        return {"feedback": [], "hidden": len(all_fb), "locked": True}
    return {"feedback": all_fb, "hidden": 0, "locked": False}


# ------------------------------------------------------------------ recruiter: candidates, links, board

class CandidateIn(BaseModel):
    name: str = Field(min_length=2)
    email: str = Field(min_length=5)
    role_title: str = Field(min_length=2)
    round_name: str = "Interview"
    length_min: int | None = None


def _new_invite(cid, round_name, length_min):
    token = secrets.token_urlsafe(16)
    ts = now_s()
    iid = ex("""INSERT INTO interviews(candidate_id, token, round_name, length_min, status, created_at, updated_at)
                VALUES (?,?,?,?, 'invited', ?, ?)""", (cid, token, round_name or "Interview", length_min, ts, ts))
    return iid, token


@router.get("/candidates")
def candidates(user=Depends(require("hr", "admin"))):
    rows = q("""SELECT c.*, u.name AS recruiter_name FROM candidates c LEFT JOIN users u ON u.id=c.recruiter_id
                ORDER BY c.id DESC""")
    return {"candidates": rows}


@router.post("/candidates")
def add_candidate(body: CandidateIn, user=Depends(require("hr", "admin"))):
    if body.length_min and body.length_min not in LENGTHS:
        raise HTTPException(400, "Length must be 30, 45 or 60")
    cid = ex("INSERT INTO candidates(name, email, role_title, recruiter_id, created_at) VALUES (?,?,?,?,?)",
             (body.name.strip(), body.email.strip(), body.role_title.strip(), user["id"], now_s()))
    iid, token = _new_invite(cid, body.round_name, body.length_min)
    mailer.send(body.email.strip(), f"Book your interview for {body.role_title}",
                f"Hello {body.name},\n\nPlease pick an interview time that suits you:\n{link_for(token)}\n\n"
                f"All times are shown in {TZ_NAME}.\n", kind="invite")
    return {"candidate_id": cid, "interview_id": iid, "link": link_for(token), "token": token}


class RoundIn(BaseModel):
    round_name: str = "Interview"
    length_min: int | None = None


@router.post("/candidates/{cid}/rounds")
def add_round(cid: int, body: RoundIn, user=Depends(require("hr", "admin"))):
    c = q1("SELECT * FROM candidates WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Candidate not found")
    iid, token = _new_invite(cid, body.round_name, body.length_min)
    mailer.send(c["email"], f"Book your {body.round_name} for {c['role_title']}",
                f"Hello {c['name']},\n\nPlease pick a time:\n{link_for(token)}\n", kind="invite")
    return {"interview_id": iid, "link": link_for(token)}


@router.get("/board")
def board(recruiter_id: int | None = None, role: str | None = None, user=Depends(require("hr", "admin"))):
    where, params = [], []
    if recruiter_id:
        where.append("c.recruiter_id=?"); params.append(recruiter_id)
    if role:
        where.append("c.role_title=?"); params.append(role)
    rows = q(IV_SELECT + (" WHERE " + " AND ".join(where) if where else "") +
             " ORDER BY CASE WHEN i.start IS NULL THEN 1 ELSE 0 END, i.start", params)
    fb = {(r["interview_id"]) for r in q("""SELECT f.interview_id FROM feedback f JOIN interviews i
                                            ON i.id=f.interview_id AND i.interviewer_id=f.interviewer_id""")}
    counts = {k: 0 for k in ("invited", "scheduled", "rescheduled", "feedback_pending", "completed", "cancelled")}
    for r in rows:
        r["board_status"] = board_status(r, fb)
        r["link"] = link_for(r["token"])
        r["calendar_sync"] = q1(
            "SELECT status, error, updated_at FROM interview_calendar_sync WHERE interview_id=?", (r["id"],))
        counts[r["board_status"]] += 1
    roles = [r["role_title"] for r in q("SELECT DISTINCT role_title FROM candidates ORDER BY role_title")]
    recruiters = q("SELECT id, name FROM users WHERE role IN ('hr','admin') AND id IN (SELECT recruiter_id FROM candidates)")
    interviewers = q("SELECT id, name, email FROM users WHERE role='interviewer' AND active=1 ORDER BY name")
    return {"interviews": rows, "counts": counts, "roles": roles, "recruiters": recruiters,
            "interviewers": interviewers, "time_zone": TZ_NAME, "now": now_s()}


@router.post("/interviews/{iid}/cancel")
def recruiter_cancel(iid: int, user=Depends(require("hr", "admin"))):
    return _cancel(iid)


@router.post("/interviews/{iid}/nudge")
def nudge(iid: int, user=Depends(require("hr", "admin"))):
    iv = q1(IV_SELECT + " WHERE i.id=?", (iid,))
    if not iv or iv["status"] != "scheduled":
        raise HTTPException(404, "Interview not found")
    notify(iv["interviewer_id"], f"Feedback reminder: {iv['candidate_name']} ({iv['round_name']})", "#/interviews")
    mailer.send(iv["interviewer_email"], f"Feedback reminder: {iv['candidate_name']}",
                f"Please submit feedback for {iv['candidate_name']} ({_fmt(iv['start'])}).\n{BASE_URL}/#/interviews",
                kind="feedback-reminder")
    return {"ok": True}


@router.post("/interviews/{iid}/calendar-sync")
def retry_calendar_sync(iid: int, user=Depends(current_user)):
    iv = q1(IV_SELECT + " WHERE i.id=?", (iid,))
    if not iv or iv["status"] not in ("scheduled", "cancelled"):
        raise HTTPException(404, "Interview not found")
    if user["role"] not in ("hr", "admin", "interviewer"):
        raise HTTPException(403, "Not allowed")
    if user["role"] == "interviewer" and iv["interviewer_id"] != user["id"]:
        raise HTTPException(404, "Interview not found")
    result = google_calendar.sync_interview(iv, cancelled=iv["status"] == "cancelled")
    if result["status"] == "failed":
        raise HTTPException(502, result["error"] or "Google Calendar synchronization failed.")
    return result


@router.get("/interviews/{iid}/ics")
def download_ics(iid: int, user=Depends(current_user)):
    iv = q1(IV_SELECT + " WHERE i.id=?", (iid,))
    if not iv or iv["status"] == "invited":
        raise HTTPException(404, "No booking yet")
    if user["role"] == "interviewer" and iv["interviewer_id"] != user["id"]:
        raise HTTPException(403, "Not your interview")
    if user["role"] not in ("interviewer", "hr", "admin"):
        raise HTTPException(403, "Not allowed")
    return Response(_ics_for(iv, cancel=iv["status"] == "cancelled"), media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="interview-{iid}.ics"'})


@router.get("/outbox")
def outbox(user=Depends(require("hr", "admin"))):
    return {"messages": q("SELECT id, at, to_addr, subject, body, kind, delivered, error, ics IS NOT NULL AS has_ics FROM outbox ORDER BY id DESC LIMIT 100"),
            "mail_ui": os.environ.get("MAIL_UI_URL", "http://localhost:8025")}


@router.get("/outbox/{oid}/ics")
def outbox_ics(oid: int, user=Depends(require("hr", "admin"))):
    m = q1("SELECT ics FROM outbox WHERE id=?", (oid,))
    if not m or not m["ics"]:
        raise HTTPException(404, "No invite attached")
    return Response(m["ics"], media_type="text/calendar", headers={"Content-Disposition": f'attachment; filename="invite-{oid}.ics"'})


@router.get("/export")
def export(user=Depends(require("hr", "admin"))):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    data = board(user=user)
    fb = {r["interview_id"]: r for r in q("SELECT * FROM feedback")}
    wb = Workbook(); ws = wb.active; ws.title = "Interviews"
    head = ["Candidate", "Email", "Role", "Round", "Recruiter", "Interviewer", "Start (IST)", "End (IST)", "Status",
            "Reschedules", "Communication", "Technical", "Problem solving", "Culture fit", "Recommendation", "Comments"]
    ws.append(head)
    for c in ws[1]: c.font = Font(bold=True)
    for r in data["interviews"]:
        f = fb.get(r["id"], {})
        ws.append([r["candidate_name"], r["candidate_email"], r["role_title"], r["round_name"], r["recruiter_name"],
                   r["interviewer_name"], (r["start"] or "").replace("T", " "), (r["end"] or "").replace("T", " "),
                   r["board_status"].replace("_", " "), r["reschedule_count"], f.get("communication"), f.get("technical"),
                   f.get("problem_solving"), f.get("culture_fit"), f.get("recommendation"), f.get("comments")])
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = max(10, min(40, max(len(str(c.value or "")) for c in col) + 2))
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="interviews_{now().strftime("%Y-%m-%d")}.xlsx"'})


# ------------------------------------------------------------------ candidate: public booking link

def _invite(token):
    iv = q1(IV_SELECT + " WHERE i.token=?", (token,))
    if not iv:
        raise HTTPException(404, "This booking link is not valid")
    return iv


@public.get("/{token}")
def booking_page(token: str):
    iv = _invite(token)
    slots = [] if iv["status"] == "cancelled" else open_slots(iv["length_min"], iv["id"])
    if iv["status"] == "scheduled":
        slots = [s for s in slots if s["id"] != iv["slot_id"]]
    slots = _calendar_free_slots(slots)
    past = iv["status"] == "scheduled" and _dt(iv["start"]) <= now()
    return {"candidate": iv["candidate_name"], "role": iv["role_title"], "round": iv["round_name"],
            "status": iv["status"], "past": past,
            "booking": None if iv["status"] != "scheduled" else {
                "start": iv["start"], "end": iv["end"], "label": _fmt(iv["start"]), "interviewer": iv["interviewer_name"],
                "location": iv["location"], "reschedules": iv["reschedule_count"]},
            "slots": [{"id": s["id"], "start": s["start"], "end": s["end"], "length_min": s["length_min"],
                       "interviewer": s["interviewer_name"]} for s in slots],
            "time_zone": TZ_NAME}


class BookIn(BaseModel):
    slot_id: int


@public.post("/{token}")
def book(token: str, body: BookIn):
    preview_iv = q1("SELECT * FROM interviews WHERE token=?", (token,))
    if not preview_iv:
        raise HTTPException(404, "This booking link is not valid")
    if preview_iv["status"] == "cancelled":
        raise HTTPException(400, "This interview was cancelled. Please contact the recruiter.")
    if preview_iv["status"] == "scheduled" and _dt(preview_iv["start"]) <= now():
        raise HTTPException(400, "This interview has already taken place")
    candidate_slots = open_slots(preview_iv["length_min"], preview_iv["id"], slot_id=body.slot_id)
    if not candidate_slots:
        raise HTTPException(409, "Sorry, that time was just taken. Please choose another slot.")
    _check_calendar_slot(candidate_slots[0])
    with tx():  # BEGIN IMMEDIATE: one booking at a time, the second sees the first's result
        iv = q1("SELECT * FROM interviews WHERE token=?", (token,))
        if not iv:
            raise HTTPException(404, "This booking link is not valid")
        if iv["status"] == "cancelled":
            raise HTTPException(400, "This interview was cancelled. Please contact the recruiter.")
        if iv["status"] == "scheduled" and _dt(iv["start"]) <= now():
            raise HTTPException(400, "This interview has already taken place")
        ok = open_slots(iv["length_min"], iv["id"], slot_id=body.slot_id)
        if not ok:
            raise HTTPException(409, "Sorry, that time was just taken. Please choose another slot.")
        s = ok[0]
        resched = iv["status"] == "scheduled"
        location = s["location"] or f"https://meet.jit.si/LeadDesk-{uuid.uuid4().hex[:12]}"
        if resched and iv["location"] and iv["location"].startswith("https://meet.jit.si/") and not s["location"]:
            location = iv["location"]  # keep the same video link on reschedule
        ex("""UPDATE interviews SET slot_id=?, interviewer_id=?, start=?, end=?, location=?, status='scheduled',
              reschedule_count=reschedule_count+?, ics_sequence=ics_sequence+?, reminder_sent=0, updated_at=? WHERE id=?""",
           (s["id"], s["interviewer_id"], s["start"], s["end"], location, int(resched), int(resched), now_s(), iv["id"]))
    full = q1(IV_SELECT + " WHERE i.id=?", (iv["id"],))
    _send_invites(full, "rescheduled" if resched else "booked", old_interviewer_id=iv["interviewer_id"] if resched else None)
    google_calendar.sync_interview(full)
    return {"ok": True, "rescheduled": resched, "label": _fmt(full["start"]), "interviewer": full["interviewer_name"],
            "location": full["location"]}


@public.get("/{token}/ics")
def booking_ics(token: str):
    iv = _invite(token)
    if iv["status"] != "scheduled":
        raise HTTPException(404, "No booking yet")
    return Response(_ics_for(iv), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="interview.ics"'})


@public.post("/{token}/cancel")
def candidate_cancel(token: str):
    iv = _invite(token)
    return _cancel(iv["id"])


def _cancel(iid):
    iv = q1(IV_SELECT + " WHERE i.id=?", (iid,))
    if not iv or iv["status"] == "cancelled":
        raise HTTPException(404, "Nothing to cancel")
    was_booked = iv["status"] == "scheduled"
    ex("UPDATE interviews SET status='cancelled', ics_sequence=ics_sequence+1, updated_at=? WHERE id=?", (now_s(), iid))
    if was_booked:
        full = q1(IV_SELECT + " WHERE i.id=?", (iid,))
        _send_invites(full, "cancelled")
        google_calendar.sync_interview(full, cancelled=True)
    return {"ok": True}


# ------------------------------------------------------------------ demo: the double-booking race

@router.post("/demo/race")
def demo_race(user=Depends(require("hr", "admin"))):
    """Two candidates book the same slot at the same instant; exactly one must win.

    Both attempts call the real booking code, on their own SQLite connections, in
    separate threads released together by a barrier. Two guards do the work:
    BEGIN IMMEDIATE serialises the writers, and a unique index allows only one live
    booking per slot. Everything the test created is removed afterwards.
    """
    free = open_slots()
    if not free:
        raise HTTPException(400, "There is no open slot left to race on. Add availability first.")
    slot = free[0]
    ts = now_s()
    made = []
    for label in ("Candidate A", "Candidate B"):
        cid = ex("INSERT INTO candidates(name, email, role_title, recruiter_id, created_at) VALUES (?,?,?,?,?)",
                 (f"{label} (race test)", "race.test@example.com", "Race test", user["id"], ts))
        iid, token = _new_invite(cid, "Race test", slot["length_min"])
        made.append({"cid": cid, "iid": iid, "token": token, "label": label})

    outbox_high = q1("SELECT COALESCE(MAX(id), 0) AS n FROM outbox")["n"]
    notif_high = q1("SELECT COALESCE(MAX(id), 0) AS n FROM notifications")["n"]
    results = []
    guard = threading.Lock()
    barrier = threading.Barrier(2)

    def attempt(row):
        try:
            barrier.wait(timeout=10)      # both threads hit book() at the same moment
        except threading.BrokenBarrierError:
            pass
        try:
            book(row["token"], BookIn(slot_id=slot["id"]))
            outcome = {"who": row["label"], "ok": True, "message": "booked"}
        except HTTPException as e:
            outcome = {"who": row["label"], "ok": False, "message": str(e.detail)}
        except Exception as e:  # noqa: BLE001 - an integrity error here still means the guard held
            outcome = {"who": row["label"], "ok": False, "message": f"{type(e).__name__}: {e}"}
        with guard:
            results.append(outcome)

    threads = [threading.Thread(target=attempt, args=(row,), daemon=True) for row in made]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    won = sum(1 for r in results if r["ok"])

    with tx():
        for row in made:
            ex("DELETE FROM interviews WHERE id=?", (row["iid"],))
            ex("DELETE FROM candidates WHERE id=?", (row["cid"],))
        ex("DELETE FROM notifications WHERE id > ?", (notif_high,))
        ex("DELETE FROM outbox WHERE id > ?", (outbox_high,))

    results.sort(key=lambda r: r["who"])
    return {"slot": slot["id"], "slot_start": _fmt(slot["start"]), "length_min": slot["length_min"],
            "bookings_made": won, "results": results}


# ------------------------------------------------------------------ background jobs

def tick():
    """Runs every minute: 24-hour reminders and nudges for missing feedback."""
    n = now()
    soon = (n + timedelta(hours=24)).isoformat(timespec="minutes")
    for iv in q(IV_SELECT + " WHERE i.status='scheduled' AND i.reminder_sent=0 AND i.start > ? AND i.start <= ?",
                (n.isoformat(timespec="minutes"), soon)):
        when = _fmt(iv["start"])
        mailer.send(iv["candidate_email"], f"Reminder: interview {when}",
                    f"Hello {iv['candidate_name']},\n\nA reminder that your interview for {iv['role_title']} is on {when}.\n"
                    f"Join / location: {iv['location']}\nChange it: {link_for(iv['token'])}\n", kind="reminder")
        mailer.send(iv["interviewer_email"], f"Reminder: {iv['candidate_name']} — {when}",
                    f"You interview {iv['candidate_name']} ({iv['role_title']}) on {when}.\nLocation: {iv['location']}\n",
                    kind="reminder")
        ex("UPDATE interviews SET reminder_sent=1 WHERE id=?", (iv["id"],))
    # Completed more than an hour ago, still no feedback -> in-app nudge once.
    cutoff = (n - timedelta(hours=1)).isoformat(timespec="minutes")
    for iv in q(IV_SELECT + """ WHERE i.status='scheduled' AND i.feedback_nudged=0 AND i.end <= ?
                               AND NOT EXISTS (SELECT 1 FROM feedback f WHERE f.interview_id=i.id)""", (cutoff,)):
        notify(iv["interviewer_id"], f"Feedback pending: {iv['candidate_name']} ({_fmt(iv['start'])})", "#/interviews")
        ex("UPDATE interviews SET feedback_nudged=1 WHERE id=?", (iv["id"],))
