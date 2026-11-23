"""Leave requests: submit from a person, approve or reject from a lead."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from .auth import current_user, require
from .db import ex, now_s, q, q1

router = APIRouter(prefix="/api", tags=["leaves"])


class LeaveIn(BaseModel):
    start_date: str = Field(min_length=10, max_length=10)
    end_date: str = Field(min_length=10, max_length=10)
    reason: str = Field(default="", max_length=1000)

    @field_validator("start_date", "end_date")
    @classmethod
    def _check_day(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Dates must be YYYY-MM-DD")
        return v


def _day(s: str) -> str:
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Dates must be YYYY-MM-DD")
    return s


@router.get("/leaves")
def leaves(user=Depends(current_user)):
    """A member sees their own leaves; a lead / admin / HR sees the whole team."""
    if user["role"] in ("lead", "admin", "hr"):
        rows = q(
            "SELECT l.id, l.user_id, l.start_date, l.end_date, l.reason, l.status, l.created_at,"
            "       u.name AS user_name, u.role AS user_role"
            "  FROM leaves l JOIN users u ON u.id = l.user_id"
            " ORDER BY l.start_date DESC, l.id DESC"
        )
        return {"leaves": rows}
    return {"leaves": q("SELECT * FROM leaves WHERE user_id=? ORDER BY start_date DESC, id DESC", (user["id"],))}


@router.post("/leaves", status_code=201)
def create_leave(body: LeaveIn, user=Depends(current_user)):
    start = _day(body.start_date)
    end = _day(body.end_date)
    if end < start:
        raise HTTPException(400, "End date must not be before the start date")
    lid = ex(
        "INSERT INTO leaves(user_id, start_date, end_date, reason, status, created_at) VALUES (?,?,?,?,?,?)",
        (user["id"], start, end, body.reason.strip(), "pending", now_s()),
    )
    return {"id": lid}


@router.post("/leaves/{lid}/decide")
def decide(lid: int, body: dict, user=Depends(require("lead", "admin", "hr"))):
    status = (body or {}).get("status")
    if status not in ("approved", "rejected"):
        raise HTTPException(422, "status must be 'approved' or 'rejected'")
    row = q1("SELECT * FROM leaves WHERE id=?", (lid,))
    if not row:
        raise HTTPException(404, "Leave not found")
    ex("UPDATE leaves SET status=?, decided_at=? WHERE id=?", (status, now_s(), lid))
    return {"id": lid, "status": status}
