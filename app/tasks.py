"""Task board, workload view, notifications and workload report export."""
import csv
import io
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .auth import current_user, require
from .db import DATA_DIR, ex, get_setting, notify, now, now_s, q, q1, set_setting, tx

router = APIRouter(prefix="/api", tags=["tasks"])

STATUSES = ["pending", "in_progress", "done", "escalated"]
STATUS_LABELS = {"pending": "Pending", "in_progress": "In progress", "done": "Done", "escalated": "Escalated"}
PRIORITIES = ["low", "medium", "high", "urgent"]
TASK_TYPES = ["Data Entry", "Reconciliation", "Claims Processing"]
OPEN = ("pending", "in_progress", "escalated")


class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    task_type: str = TASK_TYPES[0]
    assignee_id: int | None = None
    deadline: str
    priority: str = "medium"
    status: str = "pending"


class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    task_type: str | None = None
    assignee_id: int | None = None
    deadline: str | None = None
    priority: str | None = None
    status: str | None = None
    note: str | None = None


def _norm_deadline(s: str) -> str:
    try:
        return datetime.fromisoformat(s).replace(second=0, microsecond=0).isoformat(timespec="minutes")
    except ValueError:
        raise HTTPException(400, "Deadline must be a date and time")


def _event(task_id, actor_id, action, frm=None, to=None, note=None):
    ex("INSERT INTO task_events(task_id, at, actor_id, action, from_value, to_value, note) VALUES (?,?,?,?,?,?,?)",
       (task_id, now_s(), actor_id, action, frm, to, note))


def _decorate(t: dict) -> dict:
    n = now()
    dl = datetime.fromisoformat(t["deadline"])
    t["overdue"] = t["status"] != "done" and dl < n
    t["due_today"] = t["status"] != "done" and dl.date() == n.date()
    return t


TASK_SELECT = """SELECT t.*, u.name AS assignee_name, u.shift AS assignee_shift, c.name AS created_by_name
                 FROM tasks t LEFT JOIN users u ON u.id=t.assignee_id LEFT JOIN users c ON c.id=t.created_by"""


@router.get("/meta")
def meta(user=Depends(current_user)):
    members = q("SELECT id, name, shift FROM users WHERE role='member' AND active=1 ORDER BY name")
    return {"statuses": STATUSES, "status_labels": STATUS_LABELS, "priorities": PRIORITIES,
            "task_types": TASK_TYPES, "members": members,
            "overload_threshold": int(get_setting("overload_threshold", 6)), "now": now_s()}


@router.get("/tasks")
def list_tasks(status: str | None = None, assignee_id: int | None = None, mine: bool = False,
               user=Depends(current_user)):
    where, params = [], []
    if user["role"] == "member" or mine:
        where.append("t.assignee_id=?"); params.append(user["id"])
    elif user["role"] not in ("lead", "admin"):
        raise HTTPException(403, "Only team leads and members use the task board")
    if assignee_id:
        where.append("t.assignee_id=?"); params.append(assignee_id)
    if status:
        where.append("t.status=?"); params.append(status)
    sql = TASK_SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY t.deadline"
    return {"tasks": [_decorate(t) for t in q(sql, params)]}


@router.post("/tasks")
def create_task(body: TaskIn, user=Depends(require("lead", "admin"))):
    if body.priority not in PRIORITIES or body.status not in STATUSES:
        raise HTTPException(400, "Unknown priority or status")
    if body.assignee_id and not q1("SELECT id FROM users WHERE id=? AND role='member'", (body.assignee_id,)):
        raise HTTPException(400, "Unknown team member")
    ts = now_s()
    tid = ex("""INSERT INTO tasks(title, description, task_type, assignee_id, created_by, deadline, priority, status,
                created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
             (body.title.strip(), body.description, body.task_type, body.assignee_id, user["id"],
              _norm_deadline(body.deadline), body.priority, body.status, ts, ts))
    _event(tid, user["id"], "created", None, body.status)
    if body.assignee_id:
        _event(tid, user["id"], "assigned", None, str(body.assignee_id))
        notify(body.assignee_id, f"New task from {user['name']}: {body.title.strip()} "
               f"(due {_norm_deadline(body.deadline).replace('T', ' ')}, {body.priority})", f"#/my-tasks?task={tid}")
    return {"task": _decorate(q1(TASK_SELECT + " WHERE t.id=?", (tid,)))}


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskPatch, user=Depends(current_user)):
    t = q1("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t:
        raise HTTPException(404, "Task not found")
    is_lead = user["role"] in ("lead", "admin")
    if not is_lead:
        if user["role"] != "member" or t["assignee_id"] != user["id"]:
            raise HTTPException(403, "You can only update your own tasks")
        # Members may only move the status (and add a note).
        if any(v is not None for k, v in body.model_dump().items() if k not in ("status", "note")):
            raise HTTPException(403, "Only the team lead can edit task details")
    changes = body.model_dump(exclude_none=True)
    note = changes.pop("note", None)
    if "status" in changes and changes["status"] not in STATUSES:
        raise HTTPException(400, "Unknown status")
    if "priority" in changes and changes["priority"] not in PRIORITIES:
        raise HTTPException(400, "Unknown priority")
    if "deadline" in changes:
        changes["deadline"] = _norm_deadline(changes["deadline"])
    if changes.get("status") == "escalated" and not note and not is_lead:
        raise HTTPException(400, "Please say why you are escalating")
    with tx():
        for field, val in changes.items():
            old = t[field]
            if str(old) == str(val):
                continue
            ex(f"UPDATE tasks SET {field}=?, updated_at=? WHERE id=?", (val, now_s(), task_id))
            action = {"status": "status", "assignee_id": "reassigned"}.get(field, f"edited {field}")
            _event(task_id, user["id"], action, None if old is None else str(old), str(val), note)
            note = None  # attach the note to the first change only
            if field == "status":
                ex("UPDATE tasks SET done_at=? WHERE id=?", (now_s() if val == "done" else None, task_id))
                if val == "escalated":
                    for lead in q("SELECT id FROM users WHERE role='lead' AND active=1"):
                        notify(lead["id"], f"{user['name']} escalated: {t['title']}", f"#/board?task={task_id}")
            if field == "assignee_id" and val:
                notify(int(val), f"Task assigned to you: {t['title']}", f"#/my-tasks?task={task_id}")
        if note:  # a note with no field change
            _event(task_id, user["id"], "note", None, None, note)
    return {"task": _decorate(q1(TASK_SELECT + " WHERE t.id=?", (task_id,)))}


@router.get("/tasks/{task_id}/history")
def task_history(task_id: int, user=Depends(current_user)):
    t = q1("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t:
        raise HTTPException(404, "Task not found")
    if user["role"] not in ("lead", "admin") and (
        user["role"] != "member" or t["assignee_id"] != user["id"]
    ):
        raise HTTPException(403, "You cannot view this task history")
    ev = q("""SELECT e.*, u.name AS actor_name FROM task_events e LEFT JOIN users u ON u.id=e.actor_id
              WHERE task_id=? ORDER BY e.id""", (task_id,))
    names = {str(r["id"]): r["name"] for r in q("SELECT id, name FROM users")}
    for e in ev:
        if e["action"] in ("reassigned", "assigned"):
            e["from_value"] = names.get(e["from_value"], e["from_value"])
            e["to_value"] = names.get(e["to_value"], e["to_value"])
        elif e["action"] == "status" or e["action"] == "created":
            e["from_value"] = STATUS_LABELS.get(e["from_value"], e["from_value"])
            e["to_value"] = STATUS_LABELS.get(e["to_value"], e["to_value"])
    return {"events": ev}


TASK_FILES_DIR = os.path.join(DATA_DIR, "task_files")
ALLOWED_TASK_FILE_EXTS = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".zip": "application/zip"}


def _task_or_404(task_id: int):
    t = q1("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t:
        raise HTTPException(404, "Task not found")
    return t


def _can_view_task(task: dict, user: dict) -> bool:
    return user["role"] in ("lead", "admin") or (user["role"] == "member" and task["assignee_id"] == user["id"])


@router.get("/tasks/{task_id}/attachments")
def list_task_attachments(task_id: int, user=Depends(current_user)):
    t = _task_or_404(task_id)
    if not _can_view_task(t, user):
        raise HTTPException(403, "You cannot view this task")
    rows = q("""SELECT a.id, a.task_id, a.filename, a.mime, a.size, a.uploaded_by, a.uploaded_at, a.purpose,
                       u.name AS uploaded_by_name
                FROM task_attachments a LEFT JOIN users u ON u.id=a.uploaded_by
                WHERE a.task_id=? ORDER BY a.id""", (task_id,))
    return {"attachments": rows}


@router.post("/tasks/{task_id}/attachments")
async def upload_task_attachment(task_id: int, purpose: str = Form("evidence"),
                                 file: UploadFile = File(...), user=Depends(current_user)):
    t = _task_or_404(task_id)
    if not _can_view_task(t, user):
        raise HTTPException(403, "You cannot upload to this task")
    purpose = (purpose or "evidence").strip().lower()
    if purpose not in ("guide", "evidence"):
        raise HTTPException(400, "Purpose must be guide or evidence")
    if purpose == "guide" and user["role"] not in ("lead", "admin"):
        raise HTTPException(403, "Only leads can upload task guides")
    name = os.path.basename(file.filename or "file")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_TASK_FILE_EXTS:
        raise HTTPException(400, "Only PDF, DOCX, and ZIP files are allowed")
    limit = 15 * 1024 * 1024
    data = await file.read(limit + 1)
    if not data or len(data) > limit:
        raise HTTPException(400, "File is empty or larger than 15 MB")
    from .security import check_magic
    check_magic(data, name)
    os.makedirs(TASK_FILES_DIR, exist_ok=True)
    stored = f"{task_id}_{uuid.uuid4().hex}_{name}"
    path = os.path.join(TASK_FILES_DIR, stored)
    await __import__("asyncio").to_thread(Path(path).write_bytes, data)
    aid = ex("""INSERT INTO task_attachments(task_id, filename, stored_path, mime, size, uploaded_by, uploaded_at, purpose)
                VALUES (?,?,?,?,?,?,?,?)""",
             (task_id, name, stored, ALLOWED_TASK_FILE_EXTS[ext], len(data), user["id"], now_s(), purpose))
    label = "guide" if purpose == "guide" else "evidence"
    _event(task_id, user["id"], "note", None, None, f"Uploaded {label}: {name}")
    if purpose == "evidence":
        for lead in q("SELECT id FROM users WHERE role='lead' AND active=1"):
            if lead["id"] != user["id"]:
                notify(lead["id"], f"{user['name']} uploaded evidence for: {t['title']}", f"#/board?task={task_id}")
    return {"attachment": q1("""SELECT a.id, a.task_id, a.filename, a.mime, a.size, a.uploaded_by, a.uploaded_at, a.purpose,
                                       u.name AS uploaded_by_name
                                FROM task_attachments a LEFT JOIN users u ON u.id=a.uploaded_by WHERE a.id=?""", (aid,))}


@router.get("/tasks/{task_id}/attachments/{att_id}")
def download_task_attachment(task_id: int, att_id: int, user=Depends(current_user)):
    t = _task_or_404(task_id)
    if not _can_view_task(t, user):
        raise HTTPException(403, "You cannot view this task")
    a = q1("SELECT * FROM task_attachments WHERE id=? AND task_id=?", (att_id, task_id))
    if not a:
        raise HTTPException(404, "Attachment not found")
    path = os.path.join(TASK_FILES_DIR, a["stored_path"])
    if not os.path.exists(path):
        raise HTTPException(404, "File missing on disk")
    return FileResponse(path, filename=a["filename"], media_type=a["mime"])


# ---------------- workload ----------------

def workload_data(shift: str | None = None):
    threshold = int(get_setting("overload_threshold", 6))
    n = now()
    today = n.date().isoformat()
    members = q("SELECT id, name, shift FROM users WHERE role='member' AND active=1 ORDER BY name")
    if shift:
        members = [m for m in members if m["shift"] == shift]
    tasks = q("SELECT * FROM tasks WHERE assignee_id IS NOT NULL")
    rows = []
    for m in members:
        mine = [t for t in tasks if t["assignee_id"] == m["id"]]
        open_t = [t for t in mine if t["status"] in OPEN]
        r = {
            **m,
            "open": len(open_t),
            "pending": sum(t["status"] == "pending" for t in mine),
            "in_progress": sum(t["status"] == "in_progress" for t in mine),
            "escalated": sum(t["status"] == "escalated" for t in mine),
            "overdue": sum(t["deadline"] < n.isoformat(timespec="minutes") for t in open_t),
            "due_today": sum(t["deadline"][:10] == today for t in open_t),
            "done_today": sum((t["done_at"] or "")[:10] == today for t in mine if t["status"] == "done"),
            "urgent": sum(t["priority"] == "urgent" for t in open_t),
        }
        r["overloaded"] = r["open"] >= threshold
        r["needs_help"] = r["overloaded"] or r["overdue"] > 0
        rows.append(r)
    unassigned = sum(1 for t in q("SELECT status FROM tasks WHERE assignee_id IS NULL") if t["status"] in OPEN)
    totals = {
        "members": len(rows),
        "open": sum(r["open"] for r in rows) + unassigned,
        "overdue": sum(r["overdue"] for r in rows),
        "due_today": sum(r["due_today"] for r in rows),
        "escalated": sum(r["escalated"] for r in rows),
        "done_today": sum(r["done_today"] for r in rows),
        "overloaded": sum(r["overloaded"] for r in rows),
        "unassigned": unassigned,
    }
    at_risk = [_decorate(t) for t in q(TASK_SELECT + " WHERE t.status!='done' AND (t.deadline < ? OR substr(t.deadline,1,10)=? OR t.status='escalated') ORDER BY t.deadline",
                                       (n.isoformat(timespec="minutes"), today))]
    return {"threshold": threshold, "members": rows, "totals": totals, "at_risk": at_risk, "now": now_s()}


@router.get("/workload")
def workload(shift: str | None = None, user=Depends(require("lead", "admin"))):
    return workload_data(shift)


class ThresholdIn(BaseModel):
    threshold: int = Field(ge=1, le=100)


@router.put("/settings/overload-threshold")
def set_threshold(body: ThresholdIn, user=Depends(require("lead", "admin"))):
    set_setting("overload_threshold", body.threshold)
    return {"threshold": body.threshold}


@router.get("/workload/export")
def export_workload(fmt: str = "xlsx", user=Depends(require("lead", "admin"))):
    data = workload_data()
    header = ["Member", "Shift", "Open", "Pending", "In progress", "Escalated", "Overdue", "Due today",
              "Done today", f"Overloaded (>= {data['threshold']})"]
    rows = [[r["name"], r["shift"], r["open"], r["pending"], r["in_progress"], r["escalated"], r["overdue"],
             r["due_today"], r["done_today"], "YES" if r["overloaded"] else ""] for r in data["members"]]
    risk_header = ["Task", "Type", "Assignee", "Deadline", "Priority", "Status", "Overdue"]
    risk = [[t["title"], t["task_type"], t["assignee_name"] or "-", t["deadline"].replace("T", " "), t["priority"],
             STATUS_LABELS[t["status"]], "YES" if t["overdue"] else ""] for t in data["at_risk"]]
    stamp = now().strftime("%Y-%m-%d_%H%M")
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"Workload report generated {data['now']} IST"])
        w.writerow(header); w.writerows(rows); w.writerow([])
        w.writerow(["Tasks at risk"]); w.writerow(risk_header); w.writerows(risk)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="workload_{stamp}.csv"'})
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active; ws.title = "Workload"
    ws.append([f"Workload report generated {data['now']} IST"]); ws.append(header)
    for c in ws[2]: c.font = Font(bold=True)
    red = PatternFill("solid", fgColor="FDE2E1")
    for r in rows:
        ws.append(r)
        if r[-1] == "YES" or r[6]:
            for c in ws[ws.max_row]: c.fill = red
    ws2 = wb.create_sheet("At risk"); ws2.append(risk_header)
    for c in ws2[1]: c.font = Font(bold=True)
    for r in risk: ws2.append(r)
    for sheet in (ws, ws2):
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = max(10, min(45, max(len(str(c.value or "")) for c in col) + 2))
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="workload_{stamp}.xlsx"'})


# ---------------- notifications ----------------

@router.get("/notifications")
def notifications(user=Depends(current_user)):
    rows = q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 30", (user["id"],))
    unread = q1("SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND read=0", (user["id"],))["n"]
    return {"items": rows, "unread": unread}


@router.post("/notifications/read")
def mark_read(user=Depends(current_user)):
    ex("UPDATE notifications SET read=1 WHERE user_id=?", (user["id"],))
    return {"ok": True}
