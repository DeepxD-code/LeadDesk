"""Google Calendar OAuth, free/busy checks, and interview event synchronization."""
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import httpx
from cryptography.exceptions import InvalidTag

from . import crypto
from .db import ex, now, now_s, q1

log = logging.getLogger("leaddesk.google_calendar")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_URL = "https://www.googleapis.com/calendar/v3"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.events.owned "
    "https://www.googleapis.com/auth/calendar.freebusy"
)
IST = timezone(timedelta(hours=5, minutes=30))


class GoogleCalendarError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _client_id():
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def _client_secret():
    return os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()


def redirect_uri():
    configured = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if configured:
        return configured
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/iv/google/callback"


def configured():
    return bool(_client_id() and _client_secret())


def status(user_id):
    connection = q1("SELECT calendar_label, updated_at FROM google_calendar_connections WHERE user_id=?",
                    (user_id,))
    is_demo = os.environ.get("DEMO_MODE", "1") == "1"
    return {
        "configured": configured(),
        "connected": bool(connection),
        "calendar_label": connection["calendar_label"] if connection else None,
        "updated_at": connection["updated_at"] if connection else None,
        "demo_mode": is_demo,
    }


def connect_demo(user_id, calendar_label="Primary Calendar (Google Sync)"):
    tokens = {
        "access_token": "demo_token_" + secrets.token_hex(8),
        "refresh_token": "demo_refresh_" + secrets.token_hex(8),
        "expires_at": time.time() + 3600 * 24 * 30,
        "demo": True,
    }
    _save_tokens(user_id, tokens, calendar_label)
    return {"ok": True, "connected": True, "calendar_label": calendar_label}


def authorization_url(user_id):
    if not configured():
        raise GoogleCalendarError("Google Calendar is not configured on this server.")
    created = now_s()
    ex("DELETE FROM google_oauth_states WHERE created_at < ?",
       ((now() - timedelta(minutes=10)).isoformat(timespec="seconds"),))
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    ex("INSERT INTO google_oauth_states(state, user_id, code_verifier, created_at) VALUES (?,?,?,?)",
       (state, user_id, verifier, created))
    return AUTH_URL + "?" + urlencode({
        "client_id": _client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })


def _error_message(response):
    try:
        data = response.json()
    except ValueError:
        data = {}
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return error.get("message") or error.get("status") or "Google Calendar request failed."
        return data.get("error_description") or error or "Google Calendar request failed."
    return "Google Calendar request failed."


def _token_request(data):
    try:
        response = httpx.post(TOKEN_URL, data=data, timeout=15)
    except httpx.HTTPError as exc:
        raise GoogleCalendarError("Could not reach Google OAuth. Try again.") from exc
    if not response.is_success:
        raise GoogleCalendarError(f"Google OAuth failed: {_error_message(response)}", response.status_code)
    try:
        return response.json()
    except ValueError as exc:
        raise GoogleCalendarError("Google OAuth returned an invalid response.") from exc


def _decode_tokens(connection):
    try:
        dek = crypto.unwrap(bytes(connection["wrapped_key"]))
        payload = crypto.decrypt_blob(
            dek,
            bytes(connection["token_blob"]),
            f"google-calendar:{connection['user_id']}",
        )
        return json.loads(payload)
    except (InvalidTag, ValueError, json.JSONDecodeError) as exc:
        raise GoogleCalendarError("Stored Google credentials could not be decrypted. Reconnect the calendar.") from exc


def _save_tokens(user_id, tokens, calendar_label):
    connection = q1("SELECT wrapped_key FROM google_calendar_connections WHERE user_id=?", (user_id,))
    if connection:
        wrapped_key = bytes(connection["wrapped_key"])
        dek = crypto.unwrap(wrapped_key)
    else:
        dek, wrapped_key = crypto.new_file_key()
    token_blob = crypto.encrypt_blob(
        dek,
        json.dumps(tokens, separators=(",", ":")).encode(),
        f"google-calendar:{user_id}",
    )
    ex("""INSERT INTO google_calendar_connections(user_id, calendar_label, wrapped_key, token_blob, updated_at)
          VALUES (?,?,?,?,?)
          ON CONFLICT(user_id) DO UPDATE SET calendar_label=excluded.calendar_label,
          wrapped_key=excluded.wrapped_key, token_blob=excluded.token_blob, updated_at=excluded.updated_at""",
       (user_id, calendar_label, wrapped_key, token_blob, now_s()))


def complete_authorization(user_id, state, code):
    row = q1("SELECT * FROM google_oauth_states WHERE state=?", (state,))
    ex("DELETE FROM google_oauth_states WHERE state=?", (state,))
    if not row or row["user_id"] != user_id:
        raise GoogleCalendarError("Google authorization state is invalid or has expired. Start again.")
    if row["created_at"] < (now() - timedelta(minutes=10)).isoformat(timespec="seconds"):
        raise GoogleCalendarError("Google authorization expired. Start again.")
    if not code:
        raise GoogleCalendarError("Google did not return an authorization code.")

    tokens = _token_request({
        "code": code,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "redirect_uri": redirect_uri(),
        "code_verifier": row["code_verifier"],
        "grant_type": "authorization_code",
    })
    existing = q1("SELECT * FROM google_calendar_connections WHERE user_id=?", (user_id,))
    if not tokens.get("refresh_token") and existing:
        tokens["refresh_token"] = _decode_tokens(existing).get("refresh_token")
    if not tokens.get("access_token") or not tokens.get("refresh_token"):
        raise GoogleCalendarError("Google did not grant offline access. Retry and approve the requested access.")
    tokens["expires_at"] = time.time() + int(tokens.get("expires_in", 3600))

    _save_tokens(user_id, tokens, "Primary calendar")


def has_connection(user_id):
    return bool(q1("SELECT 1 FROM google_calendar_connections WHERE user_id=?", (user_id,)))


def _refresh_tokens(user_id, tokens):
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise GoogleCalendarError("Google authorization expired. Reconnect the calendar.")
    refreshed = _token_request({
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    if not refreshed.get("access_token"):
        raise GoogleCalendarError("Google did not return a refreshed access token.")
    refreshed["refresh_token"] = refreshed.get("refresh_token") or refresh_token
    refreshed["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
    connection = q1("SELECT * FROM google_calendar_connections WHERE user_id=?", (user_id,))
    _save_tokens(user_id, refreshed, connection["calendar_label"])
    return refreshed


def _access_token(user_id, force_refresh=False):
    connection = q1("SELECT * FROM google_calendar_connections WHERE user_id=?", (user_id,))
    if not connection:
        raise GoogleCalendarError("This interviewer has not connected Google Calendar.")
    tokens = _decode_tokens(connection)
    if force_refresh or float(tokens.get("expires_at", 0)) <= time.time() + 60:
        tokens = _refresh_tokens(user_id, tokens)
    return tokens["access_token"]


def _api_request(user_id, method, path, *, params=None, payload=None):
    access_token = _access_token(user_id)
    try:
        response = httpx.request(
            method,
            f"{API_URL}{path}",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            json=payload,
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise GoogleCalendarError("Could not reach Google Calendar. Try again.") from exc
    if response.status_code == 401:
        access_token = _access_token(user_id, force_refresh=True)
        try:
            response = httpx.request(
                method,
                f"{API_URL}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                json=payload,
                timeout=15,
            )
        except httpx.HTTPError as exc:
            raise GoogleCalendarError("Could not reach Google Calendar. Try again.") from exc
    if not response.is_success:
        raise GoogleCalendarError(f"Google Calendar error: {_error_message(response)}", response.status_code)
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise GoogleCalendarError("Google Calendar returned an invalid response.") from exc


def _rfc3339(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST).isoformat()


def busy_intervals(user_id, start, end):
    """Return busy intervals in IST, or None when this interviewer has not connected."""
    if not has_connection(user_id):
        return None
    connection = q1("SELECT * FROM google_calendar_connections WHERE user_id=?", (user_id,))
    if connection:
        tokens = _decode_tokens(connection)
        if tokens.get("demo"):
            today_ist = now().astimezone(IST).date()
            res = []
            for offset in range(5):
                d = today_ist + timedelta(days=offset)
                b_start = datetime(d.year, d.month, d.day, 14, 0, 0, tzinfo=IST)
                b_end = datetime(d.year, d.month, d.day, 15, 0, 0, tzinfo=IST)
                res.append((b_start, b_end))
            return res
    data = _api_request(user_id, "POST", "/freeBusy", payload={
        "timeMin": _rfc3339(start),
        "timeMax": _rfc3339(end),
        "timeZone": "Asia/Kolkata",
        "items": [{"id": "primary"}],
    })
    try:
        intervals = data["calendars"]["primary"]["busy"]
        return [
            (
                datetime.fromisoformat(item["start"].replace("Z", "+00:00")).astimezone(IST),
                datetime.fromisoformat(item["end"].replace("Z", "+00:00")).astimezone(IST),
            )
            for item in intervals
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise GoogleCalendarError("Google Calendar returned invalid availability data.") from exc


def _event_payload(interview):
    return {
        "summary": f"{interview['round_name']}: {interview['candidate_name']} | {interview['role_title']}",
        "description": (
            f"Interview for {interview['role_title']}.\n"
            f"Candidate: {interview['candidate_name']}\n"
            f"Interviewer: {interview['interviewer_name']}\n"
            f"Booking link: {os.environ.get('PUBLIC_BASE_URL', 'http://localhost:8000').rstrip('/')}"
            f"/book/{interview['token']}"
        ),
        "location": interview["location"] or "",
        "start": {"dateTime": _rfc3339(interview["start"]), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": _rfc3339(interview["end"]), "timeZone": "Asia/Kolkata"},
        "attendees": [
            {"email": interview["candidate_email"], "displayName": interview["candidate_name"]},
        ],
    }


def _save_sync(interview_id, user_id, event_id, state, error=None):
    ex("""INSERT INTO interview_calendar_sync(interview_id, calendar_user_id, event_id, status, error, updated_at)
          VALUES (?,?,?,?,?,?)
          ON CONFLICT(interview_id) DO UPDATE SET calendar_user_id=excluded.calendar_user_id,
          event_id=excluded.event_id, status=excluded.status, error=excluded.error, updated_at=excluded.updated_at""",
       (interview_id, user_id, event_id, state, error, now_s()))
    return {"status": state, "error": error}


def _delete_event(connection):
    user_id = connection["calendar_user_id"]
    event_id = connection["event_id"]
    try:
        _api_request(user_id, "DELETE", f"/calendars/primary/events/{quote(event_id, safe='')}",
                     params={"sendUpdates": "all"})
    except GoogleCalendarError as exc:
        if exc.status_code != 404:
            raise


def sync_interview(interview, *, cancelled=False):
    """Create, update, or cancel the interview event without losing the booking on API errors."""
    interview_id = interview["id"]
    existing = q1("SELECT * FROM interview_calendar_sync WHERE interview_id=?", (interview_id,))

    if cancelled:
        if not existing or not existing["event_id"]:
            return _save_sync(interview_id, interview["interviewer_id"], None, "not_connected")
        if not has_connection(existing["calendar_user_id"]):
            return _save_sync(interview_id, existing["calendar_user_id"], existing["event_id"], "failed",
                              "Reconnect the calendar to send the cancellation update.")
        try:
            _delete_event(existing)
        except GoogleCalendarError as exc:
            log.warning("Calendar cancellation failed for interview %s: %s", interview_id, exc)
            return _save_sync(interview_id, existing["calendar_user_id"], existing["event_id"], "failed", str(exc))
        return _save_sync(interview_id, existing["calendar_user_id"], None, "cancelled")

    target_user_id = interview["interviewer_id"]
    if existing and existing["event_id"] and existing["calendar_user_id"] != target_user_id:
        if not has_connection(existing["calendar_user_id"]):
            return _save_sync(interview_id, existing["calendar_user_id"], existing["event_id"], "failed",
                              "Reconnect the previous interviewer's calendar before moving this event.")
        try:
            _delete_event(existing)
        except GoogleCalendarError as exc:
            log.warning("Old calendar event removal failed for interview %s: %s", interview_id, exc)
            return _save_sync(interview_id, existing["calendar_user_id"], existing["event_id"], "failed", str(exc))
        existing = None

    if not has_connection(target_user_id):
        if existing and existing["event_id"]:
            return _save_sync(interview_id, existing["calendar_user_id"], existing["event_id"], "failed",
                              "Reconnect the calendar to update this existing event.")
        return _save_sync(interview_id, target_user_id, None, "not_connected")

    conn_row = q1("SELECT * FROM google_calendar_connections WHERE user_id=?", (target_user_id,))
    if conn_row:
        conn_tokens = _decode_tokens(conn_row)
        if conn_tokens.get("demo"):
            event_id = existing["event_id"] if existing and existing["event_id"] else f"demo_event_{interview_id:08x}"
            return _save_sync(interview_id, target_user_id, event_id, "synced")

    try:
        payload = _event_payload(interview)
        if existing and existing["event_id"]:
            data = _api_request(
                target_user_id,
                "PATCH",
                f"/calendars/primary/events/{quote(existing['event_id'], safe='')}",
                params={"sendUpdates": "all"},
                payload=payload,
            )
        else:
            stable_id = f"ld{interview_id:032x}"
            payload["id"] = stable_id
            try:
                data = _api_request(
                    target_user_id,
                    "POST",
                    "/calendars/primary/events",
                    params={"sendUpdates": "all"},
                    payload=payload,
                )
            except GoogleCalendarError as exc:
                if exc.status_code != 409:
                    raise
                data = _api_request(
                    target_user_id,
                    "GET",
                    f"/calendars/primary/events/{stable_id}",
                )
        event_id = data.get("id") or (existing["event_id"] if existing else None)
        if not event_id:
            raise GoogleCalendarError("Google Calendar did not return an event ID.")
    except GoogleCalendarError as exc:
        log.warning("Calendar event sync failed for interview %s: %s", interview_id, exc)
        return _save_sync(interview_id, target_user_id, existing["event_id"] if existing else None, "failed", str(exc))
    return _save_sync(interview_id, target_user_id, event_id, "synced")


def disconnect(user_id):
    connection = q1("SELECT * FROM google_calendar_connections WHERE user_id=?", (user_id,))
    if not connection:
        return {"ok": True}
    tokens = _decode_tokens(connection)
    if not tokens.get("demo") and tokens.get("refresh_token"):
        try:
            response = httpx.post(REVOKE_URL, data={"token": tokens["refresh_token"]}, timeout=5)
            if response.status_code >= 500:
                raise GoogleCalendarError("Google could not revoke access. Try again.")
        except httpx.HTTPError:
            pass
    ex("DELETE FROM google_calendar_connections WHERE user_id=?", (user_id,))
    return {"ok": True}
