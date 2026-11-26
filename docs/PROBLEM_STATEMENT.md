# Problem statement and requirement traceability

The brief arrived as **three problem statements**, pasted into the build session on
22 Nov 2026 (recovered from the captured session; it was never a file in the repo).
This page turns the prose into a checklist, because that is what the app is judged
against: every bullet, where it lives, and how to prove it in one action.

Status key:

- ✅ built and demonstrable
- ➕ an extra the brief called a "good addition"
- ◐ partial (stated honestly, not claimed as complete)
- ⬜ not built

## Fast proof

```bash
docker compose up --build          # http://localhost:8000
pytest tests -q                    # 55 passed
python scripts/eval_sop.py         # 5/5 answerable, 3/3 refused, 2/2 Hindi/Gujarati
ollama pull qwen2.5:3b             # optional; the app works without it
```

On the login page, **Open guided demo** signs in as the team lead and walks the
product one real API call at a time. **System proof** (also called "How we know it
works") shows the measured numbers.

---

## 1. Back-office dashboard and SOP assistant

**The brief in one line:** a team lead supervises 15–25 people, hands out work over
chat or a spreadsheet, and answers the same SOP questions all day. Build one screen
that shows the whole workload, plus an assistant that answers only from the uploaded
SOPs, cites its source, and hands over what it cannot answer. The AI runs locally and
the app deploys with Docker.

Context the brief fixes: one team of 20, two shifts, three task types, three SOPs
including an error-code guide, local AI, Docker. The seed implements all of it
(`app/seed.py`, `sample_data/`).

### Requirements

| # | Requirement | Status | Where it lives | Prove it |
|---|---|---|---|---|
| 1.01 | Lead creates a task with title, assignee, deadline, priority, status | ✅ | `POST /api/tasks` (`app/tasks.py`); Board → **New task** | create one; the card appears on the board |
| 1.02 | Statuses are pending, in progress, done, escalated | ✅ | `STATUSES` in `app/tasks.py`; board columns | board columns and the task form |
| 1.03 | Lead changes a task's status | ✅ | `PATCH /api/tasks/{id}`; drag a card | drag a card between columns |
| 1.04 | See the history of changes | ✅ | `GET /api/tasks/{id}/history`; task detail → History | open a card → History; `test_task_history_is_limited_to_leads_and_assigned_members` |
| 1.05 | Workload view: tasks per member | ✅ | `GET /api/workload`; Overview → **Team workload** | Overview chart |
| 1.06 | Overdue count | ✅ | `workload_data()`; Overview metric **Overdue** | Overview; **Overdue** tab |
| 1.07 | Tasks due today | ✅ | same; Overview metric **Due today** | Overview |
| 1.08 | Overloaded people against a threshold **the lead can set** | ✅ | `PUT /api/settings/overload-threshold`; Overview → **Limit: N tasks** | set it to 4; the overload line moves; `test_lead_sets_the_overload_threshold_and_members_cannot` |
| 1.09 | Screens usable by a non-technical person without training | ✅ | whole UI; guided demo | **Open guided demo**; labels are plain language |
| 1.10 | A one-page user guide | ✅ | `docs/USER_GUIDE.md` (96 lines) | open it |
| 1.11 | Lead uploads PDF or DOCX SOPs; the system indexes them | ✅ | `POST /api/sop/docs`; SOP library → **Upload**; `ingest_file()` | upload a PDF/DOCX; the section count appears |
| 1.12 | A team member asks a question in plain language | ✅ | `POST /api/sop/ask`; Assistant page | sign in as `m01` → Assistant |
| 1.13 | The answer is written from the documents only | ✅ | retrieval + answer gate in `app/sop.py` | `test_answerable_question_cites_a_source` |
| 1.14 | The answer shows its source: document and section | ✅ | response `source`; Assistant answer card | ask "what do I do when error 402 appears?" |
| 1.15 | When the documents do not contain the answer, it says so | ✅ | `needs_lead` branch in `app/sop.py` | `test_unanswerable_question_goes_to_the_lead` |
| 1.16 | Unanswered questions land in a "needs lead" list | ✅ | `sop_questions`; **Needs lead** page | ask about the office Wi-Fi |
| 1.17 | That list doubles as the list of SOP gaps | ✅ | Needs lead page; resolve + feedback | page copy, resolve button |
| 1.18 | ➕ Notifications for new tasks | ➕ | `notify()` in `POST /api/tasks`; bell in the rail | assign a task; the member's bell shows it |
| 1.19 | ➕ Workload report export | ➕ | `GET /api/workload/export` (xlsx + csv) | Overview → **Export report** |
| 1.20 | ➕ Hindi and Gujarati questions | ➕ | `app/lexicon.py`; no model needed | `test_hindi_question_is_answered_from_an_english_sop`, `test_gujarati_question_is_answered_from_an_english_sop`; demo step **Ask in Hindi** |

### Expected outcome

| # | Outcome | Status | Prove |
|---|---|---|---|
| O1.1 | A lead sees the team's workload on one screen | ✅ | Overview |
| O1.2 | At least 4 of 5 test questions answered correctly, with a source | ✅ **5/5** | `python scripts/eval_sop.py`; `test_admin_can_run_the_eval_in_app` |
| O1.3 | Questions the SOPs cannot answer are logged for the lead | ✅ **3/3** | Needs lead page; tests in 1.15–1.16 |

---

## 2. Secure HR document vault

**The brief in one line:** HR files sit in shared, unencrypted folders; access drifts
and nobody can say who opened what. Scans cannot be searched. Build a vault that
encrypts before writing, limits access by role, makes scans searchable with OCR, and
records every action in an audit log that ordinary users cannot edit.

Context the brief fixes: 300 employees, ~10 documents each, HR team of five, ten
sample documents of which four are scans, open-source only, keys outside the code,
Docker or one command. The seed matches (`10 documents, 4 scans`).

### Requirements

| # | Requirement | Status | Where it lives | Prove it |
|---|---|---|---|---|
| 2.01 | Encrypt uploads before storage (AES-256 or equivalent) | ✅ | `app/crypto.py` (`AES-256-GCM` envelope); `store_document()` | `test_stored_file_is_not_readable_plaintext` |
| 2.02 | Keys kept outside the code | ✅ | `secrets/vault_master.key`; `VAULT_MASTER_KEY_FILE`, optional `VAULT_MASTER_KEY_COMMAND` | `docs/SECURITY_NOTE.md`; no key in git |
| 2.03 | Show that a stored file is unreadable on disk | ✅ | `GET /api/vault/storage/{id}`; Vault → a document → **See ciphertext on disk**; demo **Show me the ciphertext** | open it: `LDV1` blob + entropy ≈ 8.0 bits/byte |
| 2.04 | Metadata: employee ID, document type, upload date | ✅ | `vault_docs` schema; document detail | every document row |
| 2.05 | Detect type (offer letter, ID proof, appraisal, other) by a rule | ✅ | `auto_type` rule in `store_document()`; upload **Detect automatically** | upload a file; the detected type and reason are shown |
| 2.06 | A user can correct the type | ✅ | `PATCH /api/vault/docs/{id}`; edit document | change the type; the audit log records it |
| 2.07 | OCR + full-text search cover scans and image PDFs | ✅ | `app/ocr.py` (pypdf → pypdfium2 → Tesseract); search over extracted text | search a phrase that exists only in a scanned sample |
| 2.08 | Highlighted matches | ✅ | `<mark>` snippets in `_snippets()`; search UI | search any phrase |
| 2.09 | Search results limited to files the user may see | ✅ | visibility filter in `search()` | `test_hr_scope_is_limited_to_their_department` |
| 2.10 | An employee sees their own documents | ✅ | `can_access()` fallback by `employee_id` | sign in as `m01` → Vault |
| 2.11 | HR sees their department | ✅ | `can_access()` HR branch | `hr1` sees only their department |
| 2.12 | Admin sees everything | ✅ | `can_access()` admin branch | `admin` → Vault |
| 2.13 | Demonstrate a request that is denied | ✅ | denial path in `_get_doc_checked()` | `test_denied_access_is_written_to_the_audit_log`; live: `m01` opens another employee's document |
| 2.14 | Audit log records upload, view, download, search with user, time, document | ✅ | `audit()` calls in `app/vault.py`; **Audit log** page | perform each action; the row appears |
| 2.15 | Ordinary users cannot edit or delete the audit log | ✅ | API has no write route; hash chain | `test_audit_log_refuses_edits_and_deletes`, `test_audit_hash_chain_is_intact` |
| 2.16 | A short security note: what is encrypted, where keys are, what is not protected, production additions | ✅ | `docs/SECURITY_NOTE.md` | open it |
| 2.17 | ➕ Retention dates | ➕ | `retention_until`; `PATCH /api/vault/docs/{id}` | `test_expired_vault_document_is_blocked_from_content_and_search` |
| 2.18 | ➕ Watermark on downloads | ➕ | `watermark()` in `app/vault.py` | download a file; the watermark carries user + time |
| 2.19 | ➕ Two-person approval for deletion | ➕ | `POST /api/vault/docs/{id}/delete-request`; `POST /api/vault/delete-requests/{id}/decide` | request as HR, approve as admin; the same person cannot approve their own request |

### Expected outcome

| # | Outcome | Status | Prove |
|---|---|---|---|
| O2.1 | Stored files cannot be read without the key | ✅ | ciphertext view; `test_stored_file_is_not_readable_plaintext` |
| O2.2 | A search for a phrase inside a scan finds the file | ✅ | search a scanned sample's phrase; highlighted snippet |
| O2.3 | A user outside the right role can neither open nor find a document | ✅ | `test_hr_scope_is_limited_to_their_department`; live denial |

---

## 3. Interview scheduler

**The brief in one line:** recruiters chase availability across messages, and feedback
arrives late in inconsistent formats. Interviewers publish slots, candidates book
from a unique link, the system prevents double booking, invites and reminders go out,
and structured feedback stays hidden until each interviewer submits their own.

Context the brief fixes: five interviewers, ten candidates in a week, interviews of
30/45/60 minutes, open-source only, a stated time zone (IST), Docker or one command.
The seed matches (`int1`–`int5`, 10 candidates).

### Requirements

| # | Requirement | Status | Where it lives | Prove it |
|---|---|---|---|---|
| 3.01 | Interviewers add one-off slots: day, start, end, length | ✅ | `POST /api/iv/slots`; Interviews → availability | add a slot; it appears in the list |
| 3.02 | Recurring slots | ✅ | `repeat_weeks` in `SlotIn`; UI **Repeat** | choose "same day for N more weeks" |
| 3.03 | A unique booking link per candidate | ✅ | per-interview `token`; **Copy link** on the board | open the link in a private window |
| 3.04 | The link shows only open slots | ✅ | `GET /api/iv/slots?token=` | `test_booking_link_shows_only_open_slots` |
| 3.05 | Confirms the chosen slot | ✅ | booking handler in `app/interviews.py`; `static/book.html` | book a slot; confirmation shows the time |
| 3.06 | Prevents double booking even when two candidates try at once | ✅ | `BEGIN IMMEDIATE` + partial unique index; demo race | `test_double_booking_race_lets_exactly_one_win`; **Simulate a race** |
| 3.07 | `.ics` invite to candidate and interviewer, with joining link or location | ✅ | `app/ics.py`; `_send_invites()` | `test_booking_a_slot_confirms_and_writes_a_calendar_invite` |
| 3.08 | Updated invites follow a reschedule | ✅ | `ics_sequence`; booking page move | move a booking from the link; invite sequence increments |
| 3.09 | Updated invites follow a cancellation | ✅ | `_cancel()` / `POST /api/iv/interviews/{id}/cancel` | cancel from the board; a cancellation mail lands in Mailpit |
| 3.10 | Reminder email 24 hours before, to a local test mail server | ✅ | `tick()` in `app/interviews.py`; Mailpit | Mailpit at http://localhost:8025 |
| 3.11 | Feedback form: rating 1–5 on four criteria | ✅ | `CRITERIA` in `app/interviews.py`; feedback form | submit feedback as `int1` |
| 3.12 | Recommendation: advance, hold or reject | ✅ | feedback schema + form | same form |
| 3.13 | Comments | ✅ | feedback schema + form | same form |
| 3.14 | Saved against that interview | ✅ | `feedback` table; `GET /api/iv/candidates/{id}/feedback` | reopen the interview |
| 3.15 | Cannot see colleagues' feedback until your own is submitted | ✅ | `feedback` visibility check | `test_feedback_is_hidden_until_you_submit_your_own` |
| 3.16 | Status board: scheduled, completed, feedback pending, rescheduled, cancelled | ✅ | `board_status()`; `GET /api/iv/board`; board pills | Interviews → Board |
| 3.17 | Filter by recruiter and role | ✅ | `recruiter_id` / `role` params on `/api/iv/board` | use the board filters |
| 3.18 | No completed interview left without feedback | ✅ | `feedback_pending` + in-app nudge in `tick()` | board count; nudge appears after the interview ends |
| 3.19 | ➕ Panel interviews | ➕ | multiple rounds per candidate (`POST /api/iv/candidates/{id}/rounds`), each with its own interviewer and independent feedback | seed has a second round with a different interviewer |
| 3.20 | ➕ Candidate self-service rescheduling | ➕ | the booking link reopens and moves the booking; `reschedule_count` | move a booking; the board says "rescheduled" |
| 3.21 | ➕ Excel export | ➕ | `GET /api/iv/export` | download from the board |

### Expected outcome

| # | Outcome | Status | Prove |
|---|---|---|---|
| O3.1 | A candidate books a slot in under a minute | ✅ | open a booking link; one click |
| O3.2 | Invites open correctly in a calendar app | ✅ | download the `.ics`; open it |
| O3.3 | Every completed interview has feedback or a visible reminder | ✅ | board **Feedback pending** + nudge |

---

## Where this deliberately stops

- **Panel interviews are multi-round, not a simultaneous panel.** Each round has one
  interviewer and independent feedback; the brief listed panels as an extra.
- **Google Calendar busy checks use the primary calendar only** (`docs/DEPLOY.md`).
  A meeting on a shared calendar does not block a LeadDesk slot yet. That is a known
  limit, stated here rather than hidden.
- **The vault's employee scope needs an `employee_id`.** `tester` and `dev` have none
  and only see the forum, by design.
- **ClamAV and off-box audit shipping are configurable and off by default.** The local
  demo runs without them; `deploy/docker-compose.prod.yml` turns ClamAV on.

## Keeping this page honest

When a requirement changes, change the row in the same commit. The two commands that
keep it checkable are:

```bash
pytest tests -q
python scripts/eval_sop.py
```
