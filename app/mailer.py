"""Outgoing mail. Every message is kept in the outbox table (visible in the app) and, when an SMTP
server is configured, also delivered to it. Docker Compose ships Mailpit as a local test mail server."""
import logging
import os
import smtplib
from email.message import EmailMessage

from .db import ex, now_s

log = logging.getLogger("leaddesk.mail")
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "1025"))
MAIL_FROM = os.environ.get("MAIL_FROM", "LeadDesk Scheduler <scheduler@leaddesk.local>")


def send(to_addr: str, subject: str, body: str, ics: str | None = None, method: str = "REQUEST", kind: str = ""):
    oid = ex("INSERT INTO outbox(at, to_addr, subject, body, ics, kind) VALUES (?,?,?,?,?,?)",
             (now_s(), to_addr, subject, body, ics, kind))
    if os.environ.get("SMTP_DISABLED") == "1":
        return oid
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = MAIL_FROM, to_addr, subject
    msg.set_content(body)
    if ics:
        # text/calendar part lets mail clients show Accept/Decline; the attachment opens in any calendar app.
        msg.add_attachment(ics.encode(), maintype="text", subtype="calendar",
                           filename="invite.ics", params={"method": method})
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5) as s:
            s.send_message(msg)
        ex("UPDATE outbox SET delivered=1 WHERE id=?", (oid,))
    except Exception as e:  # noqa: BLE001
        ex("UPDATE outbox SET error=? WHERE id=?", (str(e)[:200], oid))
        log.warning("Mail to %s not delivered (%s); kept in outbox", to_addr, e)
    return oid
