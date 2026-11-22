"""iCalendar (.ics, RFC 5545) invites. Times are written in UTC so every calendar app shows the
right local time; the app itself works in IST."""
from datetime import datetime, timezone

from .db import IST


def _utc(dt_naive_ist: datetime) -> str:
    return dt_naive_ist.replace(tzinfo=IST).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    # Lines longer than 75 octets are folded with CRLF + space.
    b = line.encode()
    if len(b) <= 75:
        return line
    out, cur = [], b""
    for ch in line:
        e = ch.encode()
        if len(cur) + len(e) > (75 if not out else 74):
            out.append(cur.decode()); cur = b""
        cur += e
    out.append(cur.decode())
    return "\r\n ".join(out)


def build_ics(uid, start: datetime, end: datetime, summary, description, location, organizer_email,
              attendees, sequence=0, cancel=False) -> str:
    method = "CANCEL" if cancel else "REQUEST"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//LeadDesk//Interview Scheduler//EN", "CALSCALE:GREGORIAN",
        f"METHOD:{method}", "BEGIN:VEVENT",
        f"UID:{uid}", f"SEQUENCE:{sequence}",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{_utc(start)}", f"DTEND:{_utc(end)}",
        f"SUMMARY:{_esc(('CANCELLED: ' if cancel else '') + summary)}",
        f"DESCRIPTION:{_esc(description)}",
        f"LOCATION:{_esc(location)}",
        f"STATUS:{'CANCELLED' if cancel else 'CONFIRMED'}",
        f"ORGANIZER;CN=LeadDesk Scheduler:mailto:{organizer_email}",
    ]
    for name, email in attendees:
        lines.append(f"ATTENDEE;CN={_esc(name)};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{email}")
    if not cancel:
        lines += ["BEGIN:VALARM", "TRIGGER:-PT30M", "ACTION:DISPLAY", "DESCRIPTION:Interview in 30 minutes", "END:VALARM"]
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
