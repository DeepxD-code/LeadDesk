"""SQLite storage. One file, WAL mode, schema created on startup."""
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
DB_PATH = os.path.join(DATA_DIR, "leaddesk.db")

# The whole app works in Indian Standard Time (UTC+05:30, no daylight saving).
IST = timezone(timedelta(hours=5, minutes=30), "IST")
TZ_NAME = "Asia/Kolkata (IST, UTC+05:30)"


def now() -> datetime:
    """Current IST time as a naive datetime (all stored times are naive IST)."""
    return datetime.now(IST).replace(tzinfo=None, microsecond=0)


def now_s() -> str:
    return now().isoformat(timespec="seconds")


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


_local = threading.local()


def connect() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = connect()
        _local.conn = conn
    return conn


def q(sql, params=()):
    return [dict(r) for r in get_conn().execute(sql, params).fetchall()]


def q1(sql, params=()):
    r = get_conn().execute(sql, params).fetchone()
    return dict(r) if r else None


def ex(sql, params=()):
    cur = get_conn().execute(sql, params)
    return cur.lastrowid


@contextmanager
def tx(immediate=True):
    """Explicit transaction. BEGIN IMMEDIATE takes the write lock up front, so two
    concurrent writers are serialised (used for booking to stop double booking)."""
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,              -- lead | member | admin | hr | interviewer | tester | developer
  employee_id TEXT,
  department TEXT,
  shift TEXT,
  email TEXT,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  at TEXT NOT NULL,
  text TEXT NOT NULL,
  link TEXT,
  read INTEGER NOT NULL DEFAULT 0
);

-- ---------- Task board ----------
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  task_type TEXT NOT NULL,
  assignee_id INTEGER REFERENCES users(id),
  created_by INTEGER REFERENCES users(id),
  deadline TEXT NOT NULL,
  priority TEXT NOT NULL,          -- low | medium | high | urgent
  status TEXT NOT NULL,            -- pending | in_progress | done | escalated
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  done_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_tasks_assignee ON tasks(assignee_id, status);
CREATE TABLE IF NOT EXISTS task_events (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  at TEXT NOT NULL,
  actor_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL,
  from_value TEXT,
  to_value TEXT,
  note TEXT
);

-- ---------- SOP assistant ----------
CREATE TABLE IF NOT EXISTS sop_docs (
  id INTEGER PRIMARY KEY,
  filename TEXT NOT NULL,
  title TEXT NOT NULL,
  uploaded_by INTEGER REFERENCES users(id),
  uploaded_at TEXT NOT NULL,
  n_sections INTEGER NOT NULL DEFAULT 0,
  stored_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sop_chunks (
  id INTEGER PRIMARY KEY,
  doc_id INTEGER NOT NULL REFERENCES sop_docs(id) ON DELETE CASCADE,
  section TEXT NOT NULL,
  text TEXT NOT NULL,
  ord INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  asked_at TEXT NOT NULL,
  question TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT 'en',
  answer TEXT,
  sources TEXT,                    -- JSON list of {doc, section}
  status TEXT NOT NULL,            -- answered | needs_lead | resolved
  top_score REAL,
  mode TEXT,                       -- llm | extractive
  lead_answer TEXT,
  resolved_by INTEGER REFERENCES users(id),
  resolved_at TEXT,
  helpful INTEGER
);

-- ---------- HR vault ----------
CREATE TABLE IF NOT EXISTS employees (
  employee_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  department TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vault_docs (
  id INTEGER PRIMARY KEY,
  employee_id TEXT NOT NULL REFERENCES employees(employee_id),
  department TEXT NOT NULL,
  doc_type TEXT NOT NULL,          -- offer_letter | id_proof | appraisal | other
  doc_type_source TEXT NOT NULL,   -- rule | user
  type_reason TEXT,
  original_name TEXT NOT NULL,
  mime TEXT NOT NULL,
  size INTEGER NOT NULL,
  uploaded_by INTEGER REFERENCES users(id),
  uploaded_at TEXT NOT NULL,
  retention_until TEXT,
  storage_name TEXT NOT NULL,
  wrapped_key BLOB NOT NULL,
  sha256 TEXT NOT NULL,
  ocr_used INTEGER NOT NULL DEFAULT 0,
  text_enc BLOB,                   -- extracted/OCR text, encrypted with the same file key
  deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS vault_delete_requests (
  id INTEGER PRIMARY KEY,
  doc_id INTEGER NOT NULL REFERENCES vault_docs(id),
  requested_by INTEGER NOT NULL REFERENCES users(id),
  requested_at TEXT NOT NULL,
  reason TEXT,
  approved_by INTEGER REFERENCES users(id),
  approved_at TEXT,
  status TEXT NOT NULL DEFAULT 'pending'   -- pending | approved | rejected
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  user_id INTEGER,
  username TEXT,
  role TEXT,
  action TEXT NOT NULL,            -- upload | view | download | search | denied | ...
  doc_id INTEGER,
  detail TEXT,
  outcome TEXT NOT NULL,           -- allowed | denied
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
-- The audit log is append-only: the database itself refuses edits and deletes.
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

-- ---------- Interview scheduler ----------
CREATE TABLE IF NOT EXISTS slots (
  id INTEGER PRIMARY KEY,
  interviewer_id INTEGER NOT NULL REFERENCES users(id),
  start TEXT NOT NULL,
  end TEXT NOT NULL,
  length_min INTEGER NOT NULL,
  series_id TEXT,
  status TEXT NOT NULL DEFAULT 'open',      -- open | removed
  location TEXT
);
CREATE INDEX IF NOT EXISTS ix_slots_int ON slots(interviewer_id, start);
CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  role_title TEXT NOT NULL,
  recruiter_id INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interviews (
  id INTEGER PRIMARY KEY,
  candidate_id INTEGER NOT NULL REFERENCES candidates(id),
  token TEXT UNIQUE NOT NULL,              -- the candidate's booking link
  round_name TEXT NOT NULL DEFAULT 'Interview',
  length_min INTEGER,                      -- restrict to this length (NULL = any)
  slot_id INTEGER REFERENCES slots(id),
  interviewer_id INTEGER REFERENCES users(id),
  start TEXT,
  end TEXT,
  location TEXT,
  status TEXT NOT NULL,                    -- invited | scheduled | cancelled
  reschedule_count INTEGER NOT NULL DEFAULT 0,
  ics_sequence INTEGER NOT NULL DEFAULT 0,
  reminder_sent INTEGER NOT NULL DEFAULT 0,
  feedback_nudged INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
-- A slot can carry at most one live booking. This is the database-level guard
-- against double booking, on top of the locked transaction in the booking code.
CREATE UNIQUE INDEX IF NOT EXISTS ux_interview_slot_live ON interviews(slot_id) WHERE status = 'scheduled';
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY,
  interview_id INTEGER NOT NULL REFERENCES interviews(id),
  interviewer_id INTEGER NOT NULL REFERENCES users(id),
  communication INTEGER NOT NULL,
  technical INTEGER NOT NULL,
  problem_solving INTEGER NOT NULL,
  culture_fit INTEGER NOT NULL,
  recommendation TEXT NOT NULL,            -- advance | hold | reject
  comments TEXT,
  submitted_at TEXT NOT NULL,
  UNIQUE(interview_id, interviewer_id)
);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  to_addr TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  ics TEXT,
  kind TEXT,
  delivered INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

-- ---------- Team forum ----------
CREATE TABLE IF NOT EXISTS forum_posts (
  id INTEGER PRIMARY KEY,
  author_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_forum_posts_updated ON forum_posts(updated_at DESC, id DESC);
CREATE TABLE IF NOT EXISTS forum_replies (
  id INTEGER PRIMARY KEY,
  post_id INTEGER NOT NULL REFERENCES forum_posts(id) ON DELETE CASCADE,
  author_id INTEGER NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_forum_replies_post ON forum_replies(post_id, id);
"""


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    if not q1("SELECT value FROM settings WHERE key='overload_threshold'"):
        ex("INSERT INTO settings(key, value) VALUES ('overload_threshold', '6')")


def get_setting(key, default=None):
    r = q1("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key, value):
    ex("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
       (key, str(value)))


def notify(user_id, text, link=None):
    ex("INSERT INTO notifications(user_id, at, text, link) VALUES (?,?,?,?)", (user_id, now_s(), text, link))
