"""Demo data: one team of 20 on two shifts, 3 task types, 3 SOPs, 300 employees + 10 HR documents,
5 interviewers / 10 candidates. All fictional. Demo password for every account: see README (DEMO_PASSWORD)."""
import logging
import os
import random
import shutil
from datetime import datetime, timedelta

from .auth import hash_password
from .db import DATA_DIR, ex, now, q, q1, tx

log = logging.getLogger("leaddesk.seed")
ROOT = os.path.dirname(os.path.dirname(__file__))
SAMPLES = os.path.join(ROOT, "sample_data")
PASSWORD = os.environ.get("DEMO_PASSWORD", "demo1234")

FIRST = ["Riya", "Arjun", "Sahil", "Pooja", "Neha", "Vikram", "Ananya", "Rohan", "Isha", "Karan", "Divya", "Aditya",
         "Sneha", "Manish", "Kavya", "Harsh", "Nidhi", "Yash", "Priyanka", "Dev", "Meera", "Kabir", "Tanvi", "Aarav",
         "Simran", "Rahul", "Jhanvi", "Parth", "Hetal", "Bhavin"]
LAST = ["Sharma", "Mehta", "Verma", "Patel", "Shah", "Iyer", "Nair", "Desai", "Joshi", "Trivedi", "Rao", "Gupta",
        "Kapoor", "Bhatt", "Pandya", "Reddy", "Chauhan", "Modi", "Kulkarni", "Agarwal"]
DEPTS = ["Operations", "Finance", "Sales", "Technology", "Human Resources"]


def _user(username, name, role, employee_id=None, department=None, shift=None):
    return ex("""INSERT INTO users(username, name, password_hash, role, employee_id, department, shift, email)
                 VALUES (?,?,?,?,?,?,?,?)""",
              (username, name, hash_password(PASSWORD), role, employee_id, department, shift, f"{username}@leaddesk.local"))


def seed_people():
    rnd = random.Random(11)
    # 300 employees. EMP0001-0020 are the operations team (the 20 team members); fixed names match the sample docs.
    fixed = {"EMP0001": "Riya Sharma", "EMP0002": "Arjun Mehta", "EMP0003": "Sahil Verma", "EMP0120": "Kabir Nair",
             "EMP0121": "Meera Iyer", "EMP0210": "Tanvi Desai"}
    used = set(fixed.values())
    with tx():
        for i in range(1, 301):
            eid = f"EMP{i:04d}"
            dept = ("Operations" if i <= 100 else "Finance" if i <= 150 else "Technology" if i <= 200
                    else "Sales" if i <= 250 else "Human Resources")
            name = fixed.get(eid)
            while not name:
                cand = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
                if cand not in used:
                    name = cand
            used.add(name)
            ex("INSERT INTO employees(employee_id, name, department) VALUES (?,?,?)", (eid, name, dept))
        emps = {r["employee_id"]: r for r in q("SELECT * FROM employees")}
        _user("lead", "Priya Kulkarni", "lead", "EMP0090", "Operations")
        for i in range(1, 21):
            eid = f"EMP{i:04d}"
            _user(f"m{i:02d}", emps[eid]["name"], "member", eid, "Operations", "Morning" if i <= 10 else "Evening")
        _user("admin", "Anil Rao (Admin)", "admin", "EMP0280", "Human Resources")
        _user("admin2", "Farah Khan (Admin)", "admin", "EMP0281", "Human Resources")
        for n, dept in enumerate(DEPTS, 1):
            eid = f"EMP{270 + n:04d}"
            _user(f"hr{n}", f"{emps[eid]['name']} (HR)", "hr", eid, dept)
        for n, nm in enumerate(["Nikhil Joshi", "Sonal Bhatt", "Ramesh Iyer", "Alisha Gupta", "Varun Pandya"], 1):
            _user(f"int{n}", nm, "interviewer", None, "Operations")


TASKS = {
    "Data Entry": ["Key in vendor invoices batch {n}", "Update KYC fields for client batch {n}", "Enter claim forms - courier lot {n}",
                   "Capture purchase orders lot {n}", "Digitise bank mandates set {n}"],
    "Reconciliation": ["Reconcile HDFC current account - day {n}", "Match vendor ledger vs statement #{n}",
                       "Clear suspense items list {n}", "Card settlement reconciliation run {n}", "GST input credit match #{n}"],
    "Claims Processing": ["Process medical claims queue {n}", "Verify reimbursement claims lot {n}", "Refund requests batch {n}",
                          "Duplicate payment check - case {n}", "Motor claims document check {n}"],
}


def seed_tasks():
    rnd = random.Random(5)
    lead = q1("SELECT id FROM users WHERE username='lead'")["id"]
    members = q("SELECT id, username FROM users WHERE role='member' ORDER BY username")
    n0 = now().replace(second=0)
    # Load shapes: two people clearly overloaded, a few busy, the rest normal.
    load = {m["id"]: 3 for m in members}
    load[members[3]["id"]] = 9   # m04 overloaded
    load[members[13]["id"]] = 8  # m14 overloaded
    load[members[6]["id"]] = 5; load[members[16]["id"]] = 5; load[members[0]["id"]] = 4
    counter = 100
    with tx():
        for m in members:
            for k in range(load[m["id"]] + rnd.randint(1, 3)):  # open ones + some done
                counter += 1
                ttype = rnd.choice(list(TASKS))
                title = rnd.choice(TASKS[ttype]).format(n=counter)
                open_task = k < load[m["id"]]
                if open_task:
                    r = rnd.random()
                    if r < 0.18:
                        deadline = n0 - timedelta(hours=rnd.randint(1, 30))          # overdue
                    elif r < 0.55:
                        deadline = n0.replace(hour=rnd.choice([11, 13, 15, 17, 19, 21]), minute=rnd.choice([0, 30]))
                        if deadline < n0:
                            deadline = n0 + timedelta(minutes=rnd.randint(30, 200))
                    else:
                        deadline = n0 + timedelta(days=rnd.randint(1, 4), hours=rnd.randint(0, 6))
                    status = rnd.choices(["pending", "in_progress", "escalated"], [5, 4, 1])[0]
                else:
                    deadline = n0 - timedelta(hours=rnd.randint(2, 40))
                    status = "done"
                prio = rnd.choices(["low", "medium", "high", "urgent"], [2, 5, 3, 1])[0]
                created = deadline - timedelta(days=1, hours=rnd.randint(0, 8))
                created = min(created, n0 - timedelta(minutes=30))
                tid = ex("""INSERT INTO tasks(title, description, task_type, assignee_id, created_by, deadline, priority, status,
                            created_at, updated_at, done_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                         (title, "", ttype, m["id"], lead, deadline.isoformat(timespec="minutes"), prio, status,
                          created.isoformat(timespec="seconds"), created.isoformat(timespec="seconds"),
                          (deadline - timedelta(hours=1)).isoformat(timespec="seconds") if status == "done" else None))
                ex("INSERT INTO task_events(task_id, at, actor_id, action, to_value) VALUES (?,?,?,?,?)",
                   (tid, created.isoformat(timespec="seconds"), lead, "created", "pending"))
                ex("INSERT INTO task_events(task_id, at, actor_id, action, to_value) VALUES (?,?,?,?,?)",
                   (tid, created.isoformat(timespec="seconds"), lead, "assigned", str(m["id"])))
                t = created
                path = {"pending": [], "in_progress": ["in_progress"], "escalated": ["in_progress", "escalated"],
                        "done": ["in_progress", "done"]}[status]
                prev = "pending"
                for st in path:
                    t = t + timedelta(minutes=rnd.randint(20, 180))
                    t = min(t, n0 - timedelta(minutes=5))
                    note = "Client has not sent the signed form; waiting since yesterday" if st == "escalated" else None
                    ex("INSERT INTO task_events(task_id, at, actor_id, action, from_value, to_value, note) VALUES (?,?,?,?,?,?,?)",
                       (tid, t.isoformat(timespec="seconds"), m["id"], "status", prev, st, note))
                    prev = st
        # Two unassigned tasks for the lead to hand out in the demo.
        for title, ttype in [("Month-end vendor statement reconciliation", "Reconciliation"),
                             ("Key in pending courier claims (lot 77)", "Claims Processing")]:
            dl = (n0 + timedelta(hours=5)).isoformat(timespec="minutes")
            tid = ex("""INSERT INTO tasks(title, task_type, assignee_id, created_by, deadline, priority, status, created_at, updated_at)
                        VALUES (?,?,NULL,?,?,?,?,?,?)""", (title, ttype, lead, dl, "high", "pending", n0.isoformat(), n0.isoformat()))
            ex("INSERT INTO task_events(task_id, at, actor_id, action, to_value) VALUES (?,?,?,?,?)",
               (tid, n0.isoformat(), lead, "created", "pending"))


def seed_sops():
    from .sop import SOP_DIR, ingest_file
    lead = q1("SELECT id FROM users WHERE username='lead'")["id"]
    os.makedirs(SOP_DIR, exist_ok=True)
    src = os.path.join(SAMPLES, "sops")
    for f in sorted(os.listdir(src)):
        dst = os.path.join(SOP_DIR, f"seed_{f}")
        shutil.copy(os.path.join(src, f), dst)
        ingest_file(dst, f, lead)
    # A few past questions so the Needs-lead list is not empty on first look.
    m = {r["username"]: r["id"] for r in q("SELECT id, username FROM users WHERE role='member'")}
    t = now() - timedelta(hours=3)
    for user, text in [("m05", "Can I work from home on Saturday if the queue is empty?"),
                       ("m12", "What do I do when error 615 appears on the payment screen?")]:
        ex("""INSERT INTO questions(user_id, asked_at, question, language, status, top_score, mode, sources)
              VALUES (?,?,?,?,?,?,?,?)""", (m[user], t.isoformat(timespec="seconds"), text, "en", "needs_lead", 0.05, "gate", "[]"))


def seed_vault():
    from . import vault
    admin = q1("SELECT * FROM users WHERE username='admin'")
    hr = {r["department"]: r for r in q("SELECT * FROM users WHERE role='hr'")}
    src = os.path.join(SAMPLES, "vault")
    for f in sorted(os.listdir(src)):
        eid = f.split("_")[0]
        emp = q1("SELECT * FROM employees WHERE employee_id=?", (eid,))
        uploader = hr.get(emp["department"], admin)
        with open(os.path.join(src, f), "rb") as fh:
            data = fh.read()
        retention = (now() + timedelta(days=365 * 7)).date().isoformat()
        vault.store_document(data, f, eid, uploader, None, retention)


def seed_interviews():
    from .interviews import _new_invite
    ints = q("SELECT * FROM users WHERE role='interviewer' ORDER BY username")
    recruiters = q("SELECT * FROM users WHERE username IN ('hr1','hr2') ORDER BY username")
    n0 = now().replace(minute=0, second=0)
    today = n0.date()
    # Availability: each interviewer, weekdays this week + next, 10:00-13:00 or 14:00-17:00 in 30/45/60 min slots.
    lengths = [30, 45, 60, 45, 30]
    with tx():
        for k, iv in enumerate(ints):
            for d in range(-3, 9):
                day = today + timedelta(days=d)
                if day.weekday() >= 5:
                    continue
                start_h = 10 if k % 2 == 0 else 14
                cur = datetime.combine(day, datetime.min.time()).replace(hour=start_h)
                end = cur + timedelta(hours=3)
                L = lengths[k]
                while cur + timedelta(minutes=L) <= end:
                    ex("INSERT INTO slots(interviewer_id, start, end, length_min, series_id, location) VALUES (?,?,?,?,?,?)",
                       (iv["id"], cur.isoformat(timespec="minutes"), (cur + timedelta(minutes=L)).isoformat(timespec="minutes"),
                        L, f"seed-{k}", None if k != 2 else "Meeting room 3, Ahmedabad office"))
                    cur += timedelta(minutes=L)
    cands = [("Aarav Shah", "Process Associate"), ("Diya Patel", "Process Associate"), ("Ishaan Rao", "Reconciliation Analyst"),
             ("Mira Joshi", "Reconciliation Analyst"), ("Kunal Trivedi", "Claims Specialist"), ("Zoya Khan", "Claims Specialist"),
             ("Neel Desai", "Process Associate"), ("Sara Thomas", "Team Lead"), ("Om Bhatt", "Reconciliation Analyst"),
             ("Leela Menon", "Claims Specialist")]
    created = []
    for i, (name, role) in enumerate(cands):
        rec = recruiters[i % 2]
        cid = ex("INSERT INTO candidates(name, email, role_title, recruiter_id, created_at) VALUES (?,?,?,?,?)",
                 (name, name.lower().replace(" ", ".") + "@example.com", role, rec["id"], (n0 - timedelta(days=4)).isoformat()))
        iid, token = _new_invite(cid, "Round 1", None)
        created.append((iid, cid))
    # Book some directly (past ones with/without feedback, upcoming ones, one rescheduled, one cancelled).
    def book_slot(iid, slot, resched=0, status="scheduled"):
        ex("""UPDATE interviews SET slot_id=?, interviewer_id=?, start=?, end=?, location=?, status=?, reschedule_count=?,
              ics_sequence=?, reminder_sent=?, updated_at=? WHERE id=?""",
           (slot["id"], slot["interviewer_id"], slot["start"], slot["end"],
            slot["location"] or f"https://meet.jit.si/LeadDesk-demo-{iid}", status, resched, resched,
            1 if slot["start"] < now().isoformat() else 0, now().isoformat(timespec="seconds"), iid))
    past = q("SELECT * FROM slots WHERE end < ? ORDER BY start DESC", (now().isoformat(timespec="minutes"),))
    future = q("SELECT * FROM slots WHERE start > ? ORDER BY start", ((now() + timedelta(hours=3)).isoformat(timespec="minutes"),))
    used = set()

    def pick(pool, avoid_int=None):
        for s in pool:
            if s["id"] in used or s["interviewer_id"] == avoid_int:
                continue
            if any(u_s["interviewer_id"] == s["interviewer_id"] and u_s["start"] < s["end"] and u_s["end"] > s["start"]
                   for u_s in [x for x in pool if x["id"] in used]):
                continue
            used.add(s["id"]); return s
        return None
    # 0-3 past: 0,1 with feedback, 2,3 feedback pending
    for j in range(4):
        s = pick(past[j * 3:])
        if s:
            book_slot(created[j][0], s)
    for j, (stars, rec, cm) in enumerate([((4, 3, 4, 5), "advance", "Clear communicator, careful with numbers."),
                                          ((2, 3, 2, 3), "hold", "Needs more practice with reconciliation logic.")]):
        iv = q1("SELECT * FROM interviews WHERE id=?", (created[j][0],))
        if iv["interviewer_id"]:
            ex("""INSERT INTO feedback(interview_id, interviewer_id, communication, technical, problem_solving, culture_fit,
                  recommendation, comments, submitted_at) VALUES (?,?,?,?,?,?,?,?,?)""",
               (iv["id"], iv["interviewer_id"], *stars, rec, cm, now().isoformat(timespec="seconds")))
    # 4-6 upcoming, 6 rescheduled once, 7 cancelled, 8-9 still waiting to book
    for j in (4, 5, 6):
        s = pick(future[j * 4:])
        if s:
            book_slot(created[j][0], s, resched=1 if j == 6 else 0)
    s = pick(future[30:])
    if s:
        book_slot(created[7][0], s, status="cancelled")
    # Second round for candidate 0 with a different interviewer (shows independent panel feedback).
    iv0 = q1("SELECT * FROM interviews WHERE id=?", (created[0][0],))
    iid2, _ = _new_invite(created[0][1], "Round 2 - Manager", None)
    s = pick(past, avoid_int=iv0["interviewer_id"])
    if s:
        book_slot(iid2, s)
        ex("""INSERT INTO feedback(interview_id, interviewer_id, communication, technical, problem_solving, culture_fit,
              recommendation, comments, submitted_at) VALUES (?,?,?,?,?,?,?,?,?)""",
           (iid2, s["interviewer_id"], 5, 4, 4, 4, "advance", "Strong ownership; would fit the evening shift.",
            now().isoformat(timespec="seconds")))


def seed_all():
    log.info("Seeding demo data…")
    seed_people()
    seed_tasks()
    seed_sops()
    seed_vault()
    seed_interviews()
    log.info("Demo data ready. Sign in as lead / m01 / hr1 / admin / int1 with the demo password.")
