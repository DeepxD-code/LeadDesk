"""Smoke tests: the app boots, roles are enforced, booking works, and the two
guards this project claims actually hold (double booking, vault encryption)."""
from fastapi.testclient import TestClient

from app.main import app


def test_health(anon):
    r = anon.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_api_needs_a_session(anon):
    assert anon.get("/api/tasks").status_code == 401
    assert anon.get("/api/vault/docs").status_code == 401


def test_wrong_password_is_refused(anon):
    r = anon.post("/api/auth/login", json={"username": "lead", "password": "nope"})
    assert r.status_code == 401


def test_demo_logins_include_tester_and_developer(anon):
    r = anon.get("/api/auth/demo-users")
    assert r.status_code == 200
    data = r.json()
    accounts = {user["username"]: user["role"] for user in data["users"]}
    assert accounts["tester"] == "tester"
    assert accounts["dev"] == "developer"
    assert data["password"] == "demo1234"


def test_tester_and_developer_can_share_forum_but_not_app_data(tester, developer, member):
    created = tester.post("/api/forum/posts", json={
        "title": "Forum smoke test",
        "body": "A tester started this discussion.",
    })
    assert created.status_code == 201
    post_id = created.json()["post"]["id"]

    assert developer.get("/api/forum/posts").json()["posts"][0]["id"] == post_id
    reply = developer.post(f"/api/forum/posts/{post_id}/replies", json={"body": "A developer replied."})
    assert reply.status_code == 201
    thread = member.get(f"/api/forum/posts/{post_id}").json()
    assert [item["author_role"] for item in thread["replies"]] == ["developer"]

    assert tester.get("/api/tasks").status_code == 403
    assert developer.get("/api/meta").status_code == 403
    assert tester.get("/api/vault/docs").status_code == 403


def test_forum_rejects_empty_messages(tester):
    response = tester.post("/api/forum/posts", json={"title": "   ", "body": "  "})
    assert response.status_code == 422


def test_lead_sees_the_whole_team_board(lead):
    tasks = lead.get("/api/tasks").json()["tasks"]
    assert len(tasks) > 20
    workload = lead.get("/api/workload").json()
    assert len(workload["members"]) == 20
    assert sum(1 for m in workload["members"] if m["overloaded"]) >= 1


def test_member_cannot_reach_the_lead_queue(member):
    assert member.get("/api/sop/questions").status_code == 403
    assert member.get("/api/vault/audit").status_code == 403


def test_member_sees_only_their_own_tasks(member):
    tasks = member.get("/api/tasks").json()["tasks"]
    assert tasks, "the demo seed should give every member work"
    assert all(t["assignee_id"] == member.get("/api/auth/me").json()["user"]["id"] for t in tasks)


def test_task_history_is_limited_to_leads_and_assigned_members(lead, member, hr):
    from app.db import q1

    member_id = member.get("/api/auth/me").json()["user"]["id"]
    own_task = q1("SELECT id FROM tasks WHERE assignee_id=? LIMIT 1", (member_id,))
    other_task = q1("SELECT id FROM tasks WHERE assignee_id!=? LIMIT 1", (member_id,))
    assert own_task and other_task

    assert member.get(f"/api/tasks/{own_task['id']}/history").status_code == 200
    assert member.get(f"/api/tasks/{other_task['id']}/history").status_code == 403
    assert lead.get(f"/api/tasks/{own_task['id']}/history").status_code == 200
    assert hr.get(f"/api/tasks/{own_task['id']}/history").status_code == 403


# ---------------------------------------------------------------- SOP assistant

def test_unanswerable_question_goes_to_the_lead(lead):
    """A question the SOPs cannot cover must not be invented — it lands in Needs lead."""
    r = lead.post("/api/sop/ask", json={"question": "What is the office Wi-Fi password?"})
    body = r.json()
    assert body["status"] == "needs_lead"
    assert body["sources"] == []


def test_answerable_question_cites_a_source(lead):
    r = lead.post("/api/sop/ask", json={"question": "Who approves a refund above 10,000?"})
    body = r.json()
    assert body["status"] in ("answered", "needs_lead")
    if body["status"] == "answered":
        assert body["sources"], "an answer must always show where it came from"


# ---------------------------------------------------------------- multilingual + retrieval

def test_lexicon_maps_domain_words_and_keeps_codes():
    from app.lexicon import lexicon_to_english

    out = lexicon_to_english("त्रुटि 402 आने पर मुझे क्या करना चाहिए?")
    assert "402" in out, "an error code must survive translation untouched"
    assert "error" in out
    assert not any("\u0900" <= ch <= "\u097F" for ch in out), "no Devanagari should be left behind"


def test_coverage_reports_unmapped_words():
    from app.lexicon import coverage

    assert coverage("त्रुटि 402") > 0
    assert coverage("plain english question") == 1.0
    # a question full of words we do not know must look low-coverage, not confident
    assert coverage("ज़ेब्रा क्वासर प्लेटिपस") < 1.0


def test_hindi_question_is_answered_from_an_english_sop(lead):
    """The brief lists Hindi as a bonus; a cold machine with no model must still answer."""
    r = lead.post("/api/sop/ask", json={"question": "त्रुटि 402 आने पर मुझे क्या करना चाहिए?"}).json()
    assert r["status"] == "answered", r
    assert r["language"] == "hi"
    assert r["sources"], "an answer must always cite a source"
    assert "Error Code Guide" in r["sources"][0]["doc"]


def test_gujarati_question_is_answered_from_an_english_sop(lead):
    r = lead.post("/api/sop/ask", json={"question": "₹10,000 થી વધુ રિફંડ કોણ મંજૂર કરે છે?"}).json()
    assert r["status"] == "answered", r
    assert r["language"] == "gu"
    assert "Claims and Payments SOP" in r["sources"][0]["doc"]
    assert "Refund" in r["sources"][0]["section"]


def test_heading_breaks_a_near_tie_between_similar_sections(lead):
    """'which form' must reach the policy titled 'Duplicate payments', not the
    'Duplicate record' error entry that merely mentions the form in passing."""
    r = lead.post("/api/sop/ask", json={"question": "Which form is used for a duplicate payment?"}).json()
    assert r["status"] == "answered", r
    assert "Claims and Payments SOP" in r["sources"][0]["doc"], r["sources"]
    assert "Duplicate payments" in r["sources"][0]["section"], r["sources"]


def test_admin_can_run_the_eval_in_app(lead):
    """The 'How we know it works' button hits this route; it must exist and score."""
    r = lead.post("/api/sop/eval")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answerable_total"] >= 5
    assert body["answerable_passed"] >= 4, "the brief asks for at least 4 of 5 with a source"
    assert body["gaps_caught"] == body["gaps_total"]


# ---------------------------------------------------------------- deployment hardening

def test_security_headers_are_on_every_response(anon):
    r = anon.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_app_csp_does_not_allow_inline_script(anon):
    """The SPA loads its code from files, so inline script stays forbidden."""
    csp = anon.get("/").headers["content-security-policy"]
    script_src = csp.split("script-src")[1].split(";")[0]
    assert "unsafe-inline" not in script_src


def test_booking_page_allows_its_own_inline_script(anon):
    """The public booking page is one self-contained file; the policy must not break it."""
    csp = anon.get("/book/anything").headers["content-security-policy"]
    script_src = csp.split("script-src")[1].split(";")[0]
    assert "unsafe-inline" in script_src


def test_login_is_throttled_after_repeated_failures(anon):
    """A password guess should stop being free. Uses a name that does not exist, so
    the counter cannot interfere with any real account in this suite."""
    codes = []
    for _ in range(6):
        codes.append(anon.post("/api/auth/login", json={"username": "no-such-user", "password": "x"}).status_code)
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def test_stale_session_is_rejected(seeded):
    """The cookie may still be in the browser; the server must refuse it anyway."""
    from datetime import timedelta

    from app.db import ex, now

    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "m02", "password": "demo1234"})
    token = r.json()["token"]
    ex("UPDATE sessions SET created_at=? WHERE token=?",
       ((now() - timedelta(hours=48)).isoformat(timespec="seconds"), token))
    r2 = c.get("/api/auth/me", headers={"X-Session": token})
    assert r2.status_code == 401
    assert "expired" in r2.json()["detail"].lower()


def test_password_change_rejects_the_demo_password(seeded):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "m03", "password": "demo1234"}).status_code == 200
    assert c.post("/api/auth/password", json={"current": "demo1234", "new": "demo1234"}).status_code == 422
    assert c.post("/api/auth/password", json={"current": "wrong", "new": "a-good-password"}).status_code == 401


def test_password_change_works_and_keeps_this_session(seeded):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "m04", "password": "demo1234"}).status_code == 200
    changed = c.post("/api/auth/password", json={"current": "demo1234", "new": "better-password-1"})
    assert changed.status_code == 200, changed.text
    # this session still works
    assert c.get("/api/auth/me").status_code == 200
    # the new password is the one that works now
    fresh = TestClient(app)
    assert fresh.post("/api/auth/login", json={"username": "m04", "password": "demo1234"}).status_code == 401
    assert fresh.post("/api/auth/login", json={"username": "m04", "password": "better-password-1"}).status_code == 200


# ---------------------------------------------------------------- vault

def test_hr_scope_is_limited_to_their_department(hr):
    """hr1 is Operations: no other department's document may be listed or searched."""
    meta = hr.get("/api/vault/meta").json()
    assert "Operations" in meta["scope"]
    for doc in hr.get("/api/vault/docs").json()["docs"]:
        assert doc["department"] == "Operations"


def test_stored_file_is_not_readable_plaintext(admin):
    """The bytes on disk must be the LDV1 ciphertext blob, not the original file."""
    doc = admin.get("/api/vault/docs").json()["docs"][0]
    raw = admin.get(f"/api/vault/storage/{doc['id']}").json()
    assert raw["disk_head_text"].startswith("LDV1"), raw["disk_head_text"]
    assert raw["sha256_matches"] is True, "the decrypted bytes must match the recorded hash"
    assert raw["entropy_bits_per_byte"] > 7.0, "ciphertext should look random"


def test_denied_access_is_written_to_the_audit_log(hr):
    """An out-of-scope document request is refused AND recorded as a denied event."""
    from app.db import q, q1

    doc = q1("SELECT id, department FROM vault_docs WHERE department != 'Operations' AND deleted=0 LIMIT 1")
    assert doc, "the seed should hold documents from other departments"
    before = q1("SELECT COUNT(*) AS n FROM audit_log WHERE outcome='denied'")["n"]

    assert hr.get(f"/api/vault/docs/{doc['id']}").status_code == 403

    denied = q("SELECT * FROM audit_log WHERE outcome='denied' ORDER BY id DESC")
    assert len(denied) == before + 1
    assert denied[0]["doc_id"] == doc["id"]
    assert denied[0]["role"] == "hr"


def test_expired_vault_document_is_blocked_from_content_and_search(admin):
    from datetime import timedelta

    from app.db import ex, now, q1

    doc = q1("SELECT id, original_name, doc_type, retention_until FROM vault_docs WHERE deleted=0 LIMIT 1")
    assert doc
    original_retention = doc["retention_until"]
    ex("UPDATE vault_docs SET retention_until=? WHERE id=?",
       ((now().date() - timedelta(days=1)).isoformat(), doc["id"]))
    try:
        assert admin.get(f"/api/vault/docs/{doc['id']}").status_code == 410
        assert admin.get(f"/api/vault/docs/{doc['id']}/file").status_code == 410
        assert admin.get(f"/api/vault/storage/{doc['id']}").status_code == 410

        listed = next(d for d in admin.get("/api/vault/docs").json()["docs"] if d["id"] == doc["id"])
        assert listed["retention_expired"] is True
        query = doc["original_name"].rsplit(".", 1)[0]
        results = admin.get("/api/vault/search", params={"qs": query}).json()["results"]
        assert doc["id"] not in {result["doc"]["id"] for result in results}

        from app.vault import DOC_TYPES

        replacement_type = next(kind for kind in DOC_TYPES if kind != doc["doc_type"])
        invalid = admin.patch(f"/api/vault/docs/{doc['id']}", json={
            "doc_type": replacement_type,
            "retention_until": "tomorrow"
        })
        assert invalid.status_code == 400
        assert q1("SELECT doc_type FROM vault_docs WHERE id=?", (doc["id"],))["doc_type"] == doc["doc_type"]

        renewed_until = (now().date() + timedelta(days=1)).isoformat()
        renewed = admin.patch(f"/api/vault/docs/{doc['id']}", json={"retention_until": renewed_until})
        assert renewed.status_code == 200, renewed.text
        assert admin.get(f"/api/vault/docs/{doc['id']}").status_code == 200
    finally:
        ex("UPDATE vault_docs SET retention_until=? WHERE id=?", (original_retention, doc["id"]))


def test_audit_log_refuses_edits_and_deletes(admin):
    """The database itself blocks UPDATE and DELETE on the audit log."""
    import sqlite3

    from app.db import DB_PATH, q1
    assert q1("SELECT COUNT(*) AS n FROM audit_log")["n"] > 0
    conn = sqlite3.connect(DB_PATH)
    try:
        for sql in ("UPDATE audit_log SET action='tampered' WHERE id=1",
                    "DELETE FROM audit_log WHERE id=1"):
            try:
                conn.execute(sql)
                conn.commit()
                raise AssertionError("the audit log accepted a write it should have refused")
            except sqlite3.DatabaseError as e:
                assert "append-only" in str(e)
    finally:
        conn.close()


def test_audit_hash_chain_is_intact(admin):
    from app.vault import verify_chain
    result = verify_chain()
    assert result["ok"] is True
    assert result["entries"] > 0


# ---------------------------------------------------------------- interviews

def test_booking_link_shows_only_open_slots(anon, seeded):
    from app.db import q1
    token = q1("SELECT token FROM interviews WHERE status='invited' LIMIT 1")["token"]
    page = anon.get(f"/book/{token}")
    assert page.status_code == 200
    assert "/api/book/" in page.text
    data = anon.get(f"/api/book/{token}").json()
    assert data["slots"], "the seeded interviewers should have availability"
    assert all(s["start"] for s in data["slots"])


def test_booking_a_slot_confirms_and_writes_a_calendar_invite(anon, seeded):
    from app.db import q1
    token = q1("SELECT token FROM interviews WHERE status='invited' LIMIT 1")["token"]
    slot = anon.get(f"/api/book/{token}").json()["slots"][0]

    booked = anon.post(f"/api/book/{token}", json={"slot_id": slot["id"]})
    assert booked.status_code == 200, booked.text

    after = anon.get(f"/api/book/{token}").json()
    assert after["status"] == "scheduled"
    assert after["booking"]["start"] == slot["start"]

    ics = anon.get(f"/api/book/{token}/ics")
    assert ics.status_code == 200
    assert "BEGIN:VCALENDAR" in ics.text and "SUMMARY" in ics.text


def test_double_booking_race_lets_exactly_one_win(hr):
    """The claim of the whole scheduler: two candidates, one slot, one winner."""
    r = hr.post("/api/iv/demo/race")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["results"]) == 2
    assert body["bookings_made"] == 1, body
    winners = [x for x in body["results"] if x["ok"]]
    losers = [x for x in body["results"] if not x["ok"]]
    assert len(winners) == 1 and len(losers) == 1
    assert "taken" in losers[0]["message"].lower() or "refused" in losers[0]["message"].lower()


def test_race_cleans_up_after_itself(hr):
    hr.post("/api/iv/demo/race")
    from app.db import q
    assert q("SELECT id FROM candidates WHERE name LIKE '%race test%'") == []
    assert q("SELECT id FROM interviews WHERE round_name='Race test'") == []


def test_feedback_is_hidden_until_you_submit_your_own(anon, seeded):
    """Structured feedback must stay independent: no peeking before submitting."""
    from app import db

    fb = db.q1("""SELECT f.interviewer_id, i.candidate_id FROM feedback f
                  JOIN interviews i ON i.id=f.interview_id LIMIT 1""")
    other = db.q1("SELECT id, username FROM users WHERE role='interviewer' AND id != ? LIMIT 1",
                  (fb["interviewer_id"],))
    # A second interviewer who has met this candidate but not yet submitted.
    db.ex("""INSERT INTO interviews(candidate_id, token, round_name, interviewer_id, status, created_at, updated_at)
             VALUES (?,?, 'Round 3 - Panel', ?, 'scheduled', ?, ?)""",
          (fb["candidate_id"], f"test-panel-{other['username']}", other["id"], db.now_s(), db.now_s()))

    tok = anon.post("/api/auth/login", json={"username": other["username"], "password": "demo1234"}).json()["token"]
    anon.cookies.clear()                       # use the header, keep this client otherwise anonymous
    r = anon.get(f"/api/iv/candidates/{fb['candidate_id']}/feedback", headers={"X-Session": tok})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["locked"] is True
    assert body["feedback"] == [], "a colleague's feedback must not be visible yet"
    assert body["hidden"] >= 1


# ---------------------------------------------------------------- leave

def test_member_submits_leave_and_lists_it(member):
    created = member.post("/api/leaves", json={"start_date": "2026-11-25", "end_date": "2026-11-26", "reason": "Personal time"})
    assert created.status_code == 201, created.text
    lid = created.json()["id"]

    mine = member.get("/api/leaves").json()["leaves"]
    assert any(l["id"] == lid for l in mine)
    assert next(l for l in mine if l["id"] == lid)["status"] == "pending"


def test_leave_rejects_bad_dates_and_reversed_ranges(member):
    assert member.post("/api/leaves", json={"start_date": "2026-13-45", "end_date": "2026-11-46"}).status_code == 422
    assert member.post("/api/leaves", json={"start_date": "2026-11-26", "end_date": "2026-11-25"}).status_code == 400


def test_lead_decides_a_leave_request(lead, member):
    created = member.post("/api/leaves", json={"start_date": "2026-12-01", "end_date": "2026-12-02", "reason": "Family event"})
    lid = created.json()["id"]
    decided = lead.post(f"/api/leaves/{lid}/decide", json={"status": "approved"})
    assert decided.status_code == 200, decided.text
    got = [l for l in lead.get("/api/leaves").json()["leaves"] if l["id"] == lid]
    assert got and got[0]["status"] == "approved"


def test_only_leads_can_decide_a_leave(member):
    created = member.post("/api/leaves", json={"start_date": "2026-12-05", "end_date": "2026-12-06"})
    lid = created.json()["id"]
    assert member.post(f"/api/leaves/{lid}/decide", json={"status": "approved"}).status_code == 403


# ---------------------------------------------------------------- re-auth & vault download

def test_vault_download_requires_reauthentication(admin):
    docs = admin.get("/api/vault/docs").json()["docs"]
    assert len(docs) > 0
    doc_id = docs[0]["id"]

    # Without re-authentication, download request is refused with 403
    r = admin.get(f"/api/vault/docs/{doc_id}/file?download=true")
    assert r.status_code == 403
    assert "Re-authentication required" in r.text

    # Wrong password fails re-auth
    bad = admin.post("/api/auth/reauth", json={"password": "wrongpassword"})
    assert bad.status_code == 401

    # Correct password succeeds
    good = admin.post("/api/auth/reauth", json={"password": "demo1234"})
    assert good.status_code == 200
    assert good.json()["ok"] is True

    # Now download succeeds with 200
    dl = admin.get(f"/api/vault/docs/{doc_id}/file?download=true")
    assert dl.status_code == 200
    assert dl.headers["Content-Disposition"].startswith("attachment;")
