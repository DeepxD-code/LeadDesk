import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app import db, google_calendar, interviews


def _make_interview(interviewer_id, recruiter_id):
    ts = db.now_s()
    candidate_id = db.ex(
        """INSERT INTO candidates(name, email, role_title, recruiter_id, created_at)
           VALUES (?,?,?,?,?)""",
        ("Test candidate", "candidate@example.com", "Operations Associate", recruiter_id, ts),
    )
    interview_id = db.ex(
        """INSERT INTO interviews(candidate_id, token, round_name, interviewer_id, status, start, end,
           created_at, updated_at) VALUES (?,?, 'Round 1', ?, 'scheduled', ?, ?, ?, ?)""",
        (candidate_id, f"feature-test-{candidate_id}", interviewer_id, "2026-11-25T10:00",
         "2026-11-25T10:45", ts, ts),
    )
    return candidate_id, interview_id


def test_interview_notes_are_private_to_hr_and_assigned_interviewer(
    interviewer, interviewer2, hr, admin, member,
):
    interviewer_user = interviewer.get("/api/auth/me").json()["user"]
    hr_user = hr.get("/api/auth/me").json()["user"]
    candidate_id, interview_id = _make_interview(interviewer_user["id"], hr_user["id"])
    try:
        created = interviewer.post(
            f"/api/iv/interviews/{interview_id}/notes",
            json={"body": "  Verify the candidate's experience with reconciliation.  "},
        )
        assert created.status_code == 201, created.text
        note = created.json()["note"]
        assert note["body"] == "Verify the candidate's experience with reconciliation."
        assert note["can_edit"] is True

        assert hr.get(f"/api/iv/interviews/{interview_id}/notes").json()["notes"][0]["body"] == note["body"]
        assert interviewer2.get(f"/api/iv/interviews/{interview_id}/notes").status_code == 404
        assert member.get(f"/api/iv/interviews/{interview_id}/notes").status_code == 404
        assert admin.get(f"/api/iv/interviews/{interview_id}/notes").status_code == 404
        assert hr.patch(f"/api/iv/notes/{note['id']}", json={"body": "Changed by HR"}).status_code == 403

        updated = interviewer.patch(f"/api/iv/notes/{note['id']}", json={"body": "Updated by the author"})
        assert updated.status_code == 200
        assert hr.get(f"/api/iv/interviews/{interview_id}/notes").json()["notes"][0]["body"] == "Updated by the author"
        assert interviewer.delete(f"/api/iv/notes/{note['id']}").status_code == 200
        assert hr.get(f"/api/iv/interviews/{interview_id}/notes").json()["notes"] == []
        assert interviewer.post(f"/api/iv/interviews/{interview_id}/notes", json={"body": "  "}).status_code == 422
    finally:
        db.ex("DELETE FROM interviews WHERE id=?", (interview_id,))
        db.ex("DELETE FROM candidates WHERE id=?", (candidate_id,))


def test_google_connect_requires_an_interviewer_and_configuration(interviewer, hr, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    status = interviewer.get("/api/iv/google/status")
    assert status.status_code == 200
    assert status.json()["configured"] is False
    assert status.json()["connected"] is False
    assert interviewer.get("/api/iv/google/connect").status_code == 503
    assert hr.get("/api/iv/google/status").status_code == 403


def test_calendar_oauth_state_is_one_time_and_tokens_are_encrypted(interviewer, monkeypatch):
    user_id = interviewer.get("/api/auth/me").json()["user"]["id"]
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://example.test/api/iv/google/callback")
    monkeypatch.setattr(google_calendar, "_token_request", lambda data: {
        "access_token": "private-access-token",
        "refresh_token": "private-refresh-token",
        "expires_in": 3600,
    })

    url = google_calendar.authorization_url(user_id)
    state = parse_qs(urlparse(url).query)["state"][0]
    try:
        google_calendar.complete_authorization(user_id, state, "temporary-code")
        connection = db.q1("SELECT * FROM google_calendar_connections WHERE user_id=?", (user_id,))
        assert connection["calendar_label"] == "Primary calendar"
        assert b"private-access-token" not in connection["token_blob"]
        assert b"private-refresh-token" not in connection["token_blob"]
        assert google_calendar._decode_tokens(connection)["refresh_token"] == "private-refresh-token"
        with pytest.raises(google_calendar.GoogleCalendarError, match="state is invalid"):
            google_calendar.complete_authorization(user_id, state, "replayed-code")
    finally:
        db.ex("DELETE FROM google_calendar_connections WHERE user_id=?", (user_id,))


def test_google_busy_period_removes_conflicting_interview_slot(monkeypatch):
    busy_start = datetime(2026, 11, 25, 10, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    busy_end = datetime(2026, 11, 25, 11, 0, tzinfo=busy_start.tzinfo)
    monkeypatch.setattr(google_calendar, "busy_intervals", lambda *_: [(busy_start, busy_end)])
    slot = {
        "interviewer_id": 41,
        "start": "2026-11-25T10:00",
        "end": "2026-11-25T10:45",
    }

    assert interviews._calendar_free_slots([slot]) == []


def test_calendar_event_sync_creates_updates_and_cancels(monkeypatch):
    interviewer_id = db.q1("SELECT id FROM users WHERE username='int1'")["id"]
    hr_id = db.q1("SELECT id FROM users WHERE username='hr1'")["id"]
    candidate_id, interview_id = _make_interview(interviewer_id, hr_id)
    calls = []

    def fake_request(user_id, method, path, **kwargs):
        calls.append((user_id, method, path, kwargs))
        return {"id": "test-google-event"}

    monkeypatch.setattr(google_calendar, "has_connection", lambda _user_id: True)
    monkeypatch.setattr(google_calendar, "_api_request", fake_request)
    interview = db.q1(interviews.IV_SELECT + " WHERE i.id=?", (interview_id,))
    try:
        assert google_calendar.sync_interview(interview)["status"] == "synced"
        interview["start"] = "2026-11-25T11:00"
        interview["end"] = "2026-11-25T11:45"
        assert google_calendar.sync_interview(interview)["status"] == "synced"
        assert google_calendar.sync_interview(interview, cancelled=True)["status"] == "cancelled"
        assert [call[1] for call in calls] == ["POST", "PATCH", "DELETE"]
        assert db.q1("SELECT status FROM interview_calendar_sync WHERE interview_id=?", (interview_id,))["status"] == "cancelled"
    finally:
        db.ex("DELETE FROM interviews WHERE id=?", (interview_id,))
        db.ex("DELETE FROM candidates WHERE id=?", (candidate_id,))

def test_creating_a_meeting_requires_a_connected_calendar(interviewer):
    user_id = db.q1("SELECT id FROM users WHERE username='int1'")["id"]
    db.ex("DELETE FROM google_calendar_connections WHERE user_id=?", (user_id,))
    bad = interviewer.post("/api/iv/google/meeting", json={
        "summary": "Ops sync", "start": "2026-11-27T16:00", "end": "2026-11-27T15:30"})
    assert bad.status_code == 400
    assert "End time" in bad.json()["detail"]
    missing = interviewer.post("/api/iv/google/meeting", json={
        "summary": "Ops sync", "start": "2026-11-27T16:00", "end": "2026-11-27T16:30"})
    assert missing.status_code == 400
    assert "Connect Google Calendar" in missing.json()["detail"]


def test_creating_a_meeting_sends_one_google_event(interviewer, monkeypatch):
    user_id = db.q1("SELECT id FROM users WHERE username='int1'")["id"]
    monkeypatch.setattr(google_calendar, "has_connection", lambda _uid: True)
    seen = {}

    def fake_create(user_id_, summary, start, end, **kwargs):
        seen.update({"user_id": user_id_, "summary": summary, "start": start, "end": end, **kwargs})
        return {"ok": True, "demo": False, "id": "evt-1", "htmlLink": "https://calendar.test/evt-1"}

    monkeypatch.setattr(google_calendar, "create_meeting", fake_create)
    invalid = interviewer.post("/api/iv/google/meeting", json={
        "summary": "Ops sync", "start": "2026-11-27T16:00", "end": "2026-11-27T16:30",
        "attendees": "a@example.com, bad-email"})
    assert invalid.status_code == 400
    ok = interviewer.post("/api/iv/google/meeting", json={
        "summary": "  Ops sync  ", "start": "2026-11-27T16:00", "end": "2026-11-27T16:30",
        "attendees": "a@example.com, A@example.com", "location": "Room 2", "description": "Agenda"})
    assert ok.status_code == 200
    assert ok.json()["id"] == "evt-1"
    assert seen["summary"] == "Ops sync"
    assert seen["attendees"] == ["a@example.com"]
    assert seen["location"] == "Room 2"
    assert seen["user_id"] == user_id

def test_meeting_create_list_edit_cancel_round_trip(interviewer, monkeypatch):
    user_id = db.q1("SELECT id FROM users WHERE username='int1'")["id"]
    monkeypatch.setattr(google_calendar, "has_connection", lambda _uid: True)
    calls = []

    def fake_create(user_id_, summary, start, end, **kwargs):
        calls.append(("create", kwargs))
        return {"ok": True, "demo": False, "id": "evt-9", "htmlLink": "https://c/9",
                "meet_link": "https://meet/9"}

    def fake_update(user_id_, calendar_id, event_id, summary, start, end, **kwargs):
        calls.append(("update", calendar_id, event_id, kwargs))
        return {"ok": True, "demo": False, "id": event_id, "htmlLink": "https://c/9", "meet_link": None}

    def fake_delete(user_id_, calendar_id, event_id):
        calls.append(("delete", calendar_id, event_id))
        return {"ok": True, "demo": False}

    monkeypatch.setattr(google_calendar, "create_meeting", fake_create)
    monkeypatch.setattr(google_calendar, "update_meeting", fake_update)
    monkeypatch.setattr(google_calendar, "delete_meeting", fake_delete)
    body = {"summary": "Team sync", "start": "2026-12-01T10:00", "end": "2026-12-01T10:30",
            "attendees": "a@example.com", "calendar_id": "team@example.com", "meet": True}
    created = interviewer.post("/api/iv/google/meeting", json=body)
    assert created.status_code == 200
    meeting_id = created.json()["meeting_id"]
    assert calls[0][1]["calendar_id"] == "team@example.com"
    assert calls[0][1]["meet"] is True
    row = db.q1("SELECT * FROM google_meetings WHERE id=?", (meeting_id,))
    assert row["user_id"] == user_id
    assert row["calendar_id"] == "team@example.com"
    assert row["meet_link"] == "https://meet/9"
    assert json.loads(row["attendees"]) == ["a@example.com"]

    listed = interviewer.get("/api/iv/google/meetings").json()["meetings"]
    assert any(m["id"] == meeting_id and m["summary"] == "Team sync" for m in listed)

    edited = interviewer.patch(f"/api/iv/google/meeting/{meeting_id}", json=body)
    assert edited.status_code == 200
    assert calls[1][0] == "update"
    assert calls[1][1] == "team@example.com"
    assert calls[1][3]["meet"] is False          # an existing Meet link is not recreated
    cancelled = interviewer.delete(f"/api/iv/google/meeting/{meeting_id}")
    assert cancelled.status_code == 200
    assert db.q1("SELECT status FROM google_meetings WHERE id=?", (meeting_id,))["status"] == "cancelled"
    assert calls[2][0] == "delete"


def test_meeting_is_private_to_its_creator(interviewer, interviewer2):
    user_id = db.q1("SELECT id FROM users WHERE username='int1'")["id"]
    ts = db.now_s()
    meeting_id = db.ex("""INSERT INTO google_meetings(user_id, calendar_id, event_id, summary, start, end,
                          attendees, location, description, meet_link, html_link, status, created_at, updated_at)
                          VALUES (?, 'primary', 'evt-private', 'Private', '2026-12-02T10:00', '2026-12-02T10:30',
                                  '[]', '', '', NULL, NULL, 'active', ?, ?)""", (user_id, ts, ts))
    try:
        body = {"summary": "Hijack", "start": "2026-12-02T10:00", "end": "2026-12-02T10:30"}
        assert interviewer2.patch(f"/api/iv/google/meeting/{meeting_id}", json=body).status_code == 404
        assert interviewer2.delete(f"/api/iv/google/meeting/{meeting_id}").status_code == 404
    finally:
        db.ex("DELETE FROM google_meetings WHERE id=?", (meeting_id,))


def test_calendars_endpoint_requires_a_connection(interviewer):
    user_id = db.q1("SELECT id FROM users WHERE username='int1'")["id"]
    db.ex("DELETE FROM google_calendar_connections WHERE user_id=?", (user_id,))
    response = interviewer.get("/api/iv/google/calendars")
    assert response.status_code == 400
    assert "Connect Google Calendar" in response.json()["detail"]
