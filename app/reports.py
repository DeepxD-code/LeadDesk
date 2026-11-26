"""Tester problem reports.

A signed-in tester can report a problem from the account menu. The report is
written to the outbox like any other message (so it is visible in the app even
when SMTP is down) and emailed to TEST_REPORT_EMAIL.
"""
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .auth import current_user
from .mailer import send

router = APIRouter(prefix="/api", tags=["reports"])

TEST_REPORT_EMAIL = os.environ.get("TEST_REPORT_EMAIL", "leaddesk-test@localhost")


class ReportIn(BaseModel):
    area: str = Field(min_length=2, max_length=60)
    severity: str = Field(pattern="^(blocker|major|minor|cosmetic)$")
    summary: str = Field(min_length=5, max_length=160)
    steps: str = Field(min_length=5, max_length=4000)
    expected: str = Field(default="", max_length=2000)
    actual: str = Field(default="", max_length=2000)
    page: str = Field(default="", max_length=300)


@router.post("/report")
def create_report(body: ReportIn, user=Depends(current_user)):
    text = f"""Tester report

From: {user['name']} ({user['username']}, {user['role']})
Page: {body.page or '(not given)'}
Area: {body.area}
Severity: {body.severity}

Summary
-------
{body.summary}

Steps to reproduce
------------------
{body.steps}

Expected
--------
{body.expected or '(not given)'}

Actual
------
{body.actual or '(not given)'}
"""
    oid = send(TEST_REPORT_EMAIL, f"[LeadDesk][{body.severity}][{body.area}] {body.summary}",
               text, kind="report")
    return {"ok": True, "id": oid, "to": TEST_REPORT_EMAIL}
