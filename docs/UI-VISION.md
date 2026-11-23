# LeadDesk UI vision: decisions log

Reference: the AKS Intelligent Systems portal (dark rail, week-grouped tracker).
This file records decisions as they are made, one rail/element at a time, so the
build never has to guess and nothing is lost between sessions.

Rule of thumb for everything below: the *pattern* is borrowed, the *content* is
LeadDesk's. No AKS text, colours or marks survive.

---

## 1. Brand plate — LOCKED

- The name shown is **Tilted Lads** (placeholder brand, may change later).
- Keep the pattern exactly: a **light plate inset in the dark rail**, holding a
  graphic mark plus the wordmark, with a small letterspaced descriptor line under
  it (`TILTED LADS` / descriptor).
- Colouring changes from the AKS violet (accent colour to be settled with the theme).
- **Not clickable.** It is a plate, not a nav item and not a home link.
- Graphic + wordmark, not a monogram-only tile.

## 2. Rail groups — LOCKED

- Two tiers: **WORK** and **PROJECTS**.
- The employee (member) login gets **nine** WORK items: Intro · My tasks · Ask the SOPs · Calendar ·
  Weekly report · Leave · Accounts · **Team forum** · **My documents**.
- Items are **not** a flat nine-line list: WORK is presented as **drop-down groups**, so the rail stays
  short for a non-technical user.
- **PROJECTS** is per role: the three task-type queues for members and leads
  (Claims & Payments, Reconciliation, Document checks), departments for HR and admin.
- Labels are **plain and verb-led**: My tasks, Ask the SOPs, Needs lead, Weekly report, Leave, Accounts.

## 2b. Team forum and mentions — SPEC (open details below)

The forum is **its own tab**, not folded into WORK, and behaves like **Discord threads**:

- People post doubts, problems or work talk, either **about a specific project/queue** or **general**.
- Working **@mentions**: a mentioned person is tagged and gets a notification **ding on the top-right bell**.
- **@all** is restricted to project managers (the `lead` role, plus admin).

This is a real build, not a label change: threads, posts, mentions, and a notification feed behind the
existing bell. Current `app/forum.py` is a flat post/reply list with no threads, no mentions, no
notifications, so it needs a schema and UI rework.

## 3. Active nav state — pending

## 4. Project spaces — pending

## 5. User footer — pending

## 6. Page header — pending

## 7. View toggle — pending

## 8. Filter chips — pending

## 9. Week group header — pending

## 10. Task row, left side — pending

## 11. Task row, right side — pending

## 12. Theme and density — pending

## 13. Scroll and stickiness — pending
