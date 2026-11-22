"""Smoke tests: the app boots, roles are enforced, booking works, and the two
guards this project claims actually hold (double booking, vault encryption)."""


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
