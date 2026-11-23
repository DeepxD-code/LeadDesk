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

## 2b. Team forum and mentions — LOCKED

The forum is **its own tab**, not folded into WORK.

- **Structure: channels containing threads.** Channels are `#general` plus one per queue/project
  (claims, reconciliation, document checks). Inside a channel, a post is a **thread** with replies,
  Discord forum-channel style.
- **Mentions:** `@name` tags a person. **@all** is restricted to **lead and admin**.
- **The bell** shows direct mentions, `@all` (to those allowed to receive it), and replies in a
  thread you started or posted in.
- Nine WORK items are therefore presented as **independent collapsible groups**, not one long list.

Build impact: `app/forum.py` today is a flat post/reply list with no threads, mentions or
notifications. This needs a schema change (`channels`, `threads`, `posts`, `mentions`, `notifications`),
API changes, and a rail-and-bell UI. Scoped as its own workstream, after the shell.

## 2c. Task detail: guide, evidence, notes — LOCKED

Every task carries three things beyond title/assignee/deadline/priority/status:

1. **Guide** — the SOP section for that queue/task type (retrieved the same way the assistant retrieves),
   **plus** a short "for this task" note the lead adds. The **AI may draft the guide only if the lead
   permits it**; it is an opt-in assist, never the default, and the lead's saved text wins.
2. **Evidence** — file uploads, **encrypted with the existing AES-256-GCM vault storage and master key**,
   with an audit entry on upload and on every view/download. No second storage path, no second key story.
3. **Notes / explanation** — free text saying what was uploaded and why, so a lead can review without
   opening every file.

**Evidence is append-only and immutable to the person who submitted it.**

- Once submitted, the employee **cannot edit or delete** it. They can still view, read and download it.
- To correct a submission they **ask the lead**; after the lead confirms, the employee uploads the new
  file and it is **appended as a new version** alongside the old one. Nothing is overwritten, so the
  history of what was claimed at the time survives.
- Visibility: **assignee, lead and admin**, audited. Not the whole team.
- **Evidence is optional to mark a task done, but flagged**: a done task with no evidence carries an
  "evidence missing" marker and is counted in the lead's attention view. Nudge, never block.

Build impact: `task_guidance` (guide text, source SOP section, author, AI-assisted flag), `task_evidence`
(append-only rows with version, uploader, bytes, hash, audit link), a correction request/approval state,
a task detail panel (today a card only shows status and history), upload handling, and audit entries.

## 3. Active nav state — LOCKED

- **Accent bar + lifted row.** My call, since you left it to me: the thin left bar plus a slightly
  lifted background is the clearest "you are here" on a dark rail, and it is what the reference does —
  we keep the pattern and recolour it to `#315d98`. The alternative (a filled pill) fights the
  attention dot and the badge for the same visual weight.
- **Badge = work waiting on me**, one rule applied per screen: open tasks on *My tasks*, unanswered
  questions on *Needs lead*, unread mentions on *Team forum*. Not totals, not vanity numbers.
- **Small line icons** beside each label, 16 px, drawn as an inline SVG sprite so the CSP stays
  `img-src 'self'` and no icon font is fetched.
- **Collapsed groups show chevron + attention dot** when any item inside has a badge, so collapsing a
  group can never hide a mention or an overdue count.
- Inactive items stay muted text; hover lifts the row without the accent bar.

## 4. Project spaces — LOCKED

- **PROJECTS is per role:** the three task-type queues for members and leads (Data Entry 43 open,
  Reconciliation 42, Claims Processing 33 — a live `GROUP BY tasks.task_type`, not invented), and
  departments for HR and admin (Operations, Human Resources, Technology, Sales, Finance).
- **Clicking a queue** opens the task board filtered to that queue, queue name in the header, with a
  clear button. No new screen.
- **Clicking a department** opens the document vault filtered to that department.
- **Queue entries carry the open count**, the same "work waiting on me" rule as the WORK badges.
- **PROJECTS is styled text-only, no icons, no chevron, always visible** — it reads as a different kind
  of navigation from WORK and never competes with the nine items above it.
- Active queue still gets the accent bar.

## 5. User footer — LOCKED

- **Identity lives in the rail footer only.** The top bar keeps the bell, the AI status pill and the
  demo person switcher; the `.who` block with role, department and shift is removed from it.
- **Shift line is live**, derived from the seeded shift schedule: `On shift · ends 18:00` while working,
  `Off shift · starts 14:00` otherwise, with the dot colour following the state.
- **Clicking the footer opens a menu**: Accounts · Change password · Sign out. This is where the new
  password feature lives, rather than as a separate button in the top bar.
- **Avatar: initials on the accent colour with a thin ring**, which is what makes it read as a person
  rather than an icon.

## 6. Page header — LOCKED

- **Title = `Screen · scope`**: `Tracker · all your tasks`, `Board · whole team`, `Vault · HR documents`.
  The first part is the screen, the second is whose or which subset.
- **Subtitle = purpose + order in plain words**: "Everything you have been given, newest first."
  No method prose, no duplicated totals.
- **Filters stick, title scrolls.** The filter bar and view toggle pin to the top; the title and subtitle
  scroll away, returning ~90 px of vertical space.
- **Page actions sit right of the title**, before the view toggle: New task, Upload SOP, Export.

## 7. View toggle — LOCKED

- Two segments switching **time scope on the same screen**: `This week` and `All weeks`.
- **Remembered per user**, so someone who lives in All weeks never re-clicks it.
- **Segmented track** with the selected segment lifted by a border — the reference's treatment.
- Only on screens where a time scope means something: My tasks, Task board, Weekly report, Interviews.
  Never on the vault or the assistant.

## 8. Filter chips — LOCKED

- **One chip per brief status, plus overdue**: `All · Pending · In progress · Done · Escalated · Overdue`.
  Overdue is computed (`deadline < now AND status <> 'done'`), not a stored status.
- **Counts always shown, including 0** — stable chip positions, and zero is information.
- **No priority filter.** Priority is visible on every row as the P-tile and the week grouping already
  orders the work; a 20-person board does not need a second filter dimension.
- One query behind the bar, so the numbers can never disagree with the rows.

## 9. Week group header — LOCKED

- **Grouping is week → day**: `WEEK 44 · MON 26 OCT – SUN 1 NOV · THIS WEEK · 9 TASKS · 1 OVERDUE`, then a
  day sub-header `Mon 26 Oct · 3 tasks`, then the rows.
- **Time is out.** No estimate or actual minutes. The tracker reports volume, status and overdue — not
  hours — and the Weekly report is a record of what was done, not how long it took.
- **Overdue replaces the time segment**, because overdue is the number the brief actually cares about and
  the chip already computes it.
- **The week header pins** under the filter bar; day headers scroll with their group.
- **Days with no tasks are skipped**, so a quiet week is two lines instead of seven empty bands.

## 10. Task row, left side — LOCKED

- **Priority is a P1–P4 colour tile**, mapped from the brief's own words: urgent→P1, high→P2, medium→P3,
  low→P4. The words still appear in the tooltip and the create form; the row does not spend width on them.
- **Tasks get an auto code per queue**: `DE-014`, `RC-007`, `CP-031`. Short, speakable in chat, and a row
  becomes addressable in an @mention without quoting its title.
- **The muted line under the title carries type + assignee**: `Data Entry · Meera Iyer`. Type explains the
  kind of work, assignee answers "whose" without switching screens — and it is the one field a lead
  scanning the board needs most.
- **Titles clamp to two lines** with an ellipsis, keeping row heights predictable.

## 11. Task row, right side — LOCKED

- **Status = coloured dot + word**: green Done, grey Pending, blue In progress, red Escalated.
- **Middle slot = the deadline**, turning red and phrased as `2 days late` once past.
- **Far right = the completion date, only on done tasks**; blank otherwise. Each fact appears exactly once.
- **Guide, evidence and notes live only inside the task detail panel** — the row stays clean.
- **The one exception: a done task with no evidence carries a small red "no evidence" marker** on its row,
  and the lead's attention view counts it. Since evidence is optional but flagged, the flag has to be
  visible where a lead already looks.

## 12. Theme and density — LOCKED

- **Dark rail, light content.** The rail is near-black; the content area keeps the current warm off-white
  surfaces. Least rework, keeps `docs/DESIGN.md`'s "operate, don't decorate" tone, and gives the light-on-
  dark brand plate something to sit in.
- **Accent is two tones of the same blue** (my call, measured):
  - `#315d98` on **light** surfaces — fills, buttons, links in content (white on it is 6.67:1).
  - `#5b8fd6` on the **dark rail** — active bar, icons, emphasis (5.78:1 on `#0f0f13`).
  - The locked `#315d98` alone is 2.87:1 on near-black and fails the 3:1 minimum for UI components, which
    is exactly the "your wish" gap this fills.
- **Density is user-switchable**: comfortable (~72 px rows, two-line left block) and compact (~52 px rows).
  The choice is remembered per user, the same way the week/all-weeks toggle is.
- **Surfaces: subtle shadows on the light content, borders on the dark rail.** Shadows are invisible on
  near-black, so they are spent where they read: cards, popovers, the task detail panel. Radius stays 10 px.

## 13. Scroll and stickiness — LOCKED

- **Responsive ladder: label rail → icon rail → drawer.** Full rail with labels above ~1100 px, icon-only
  rail (~56 px, labels on hover) between ~1100 and ~760, slide-out drawer below that.
- **The rail never scrolls.** The plate stays top, the identity footer stays bottom, and if the middle would
  overflow the groups collapse to their headers rather than introducing a second scrollbar.
- **Phone: drawer behind a hamburger plus a bottom tab bar** with the four most used screens (My tasks,
  Ask the SOPs, Team forum, More). Thumb-reachable.
- **Thin sticky top bar** holding the bell, the AI status pill and the demo person switcher — never scrolls
  away, so the notification count is always visible.
- Page level: title scrolls, filters stick, week header pins (item 6 and item 9).

---

## Prototype (sketch, Oct 26 2026)

A clickable prototype of the shell exists at `prototype/shell-prototype.html` — open it in a browser.
It is **placeholder data only** (no real content): every role is available through the "Sign in as"
prototype bar, and every tab — including the cut-off MVP pages — is a sketched placeholder page that
follows the same shell grammar (title + actions, chips, sticky filters, week→day tracker or a short
list, slide-over detail) rather than real data.

Verified behaviors: rail group toggles, attention dots, per-role PROJECTS tiers, view toggles,
week/all-weeks filter, task-detail panel (guide, evidence versions, notes, immutable-note text,
correction button), forum with channels/threads/mentions (`@all` restricted to lead and admin),
dark rail + light content, density, and the phone drawer. Screenshots live in
`prototype/shots/` — `01-member.png` (member home), `02-lead.png` (lead tracker), `06-forum.png`
(forum), `10-drawer.png` (phone drawer open).

---

## Build order

Nothing above is built yet. Dependencies point to this sequence:

1. **Shell** — rail with tiers, collapsible groups, icons, active state, identity footer, top bar, dark
   rail + light content, density switch. Pure `app.js` / `styles.css`; no schema change, works on today's
   data.
2. **Task data model** — auto codes, deadline logic, `task_guidance`, `task_evidence` (encrypted, append-
   only, correction approval), notes, task detail panel.
3. **Tracker views** — week → day grouping, chips with counts, sticky filters, page headers, view toggle.
4. **Forum** — channels, threads, mentions, `@all` restriction, notifications behind the bell.
5. **New MVPs** — Calendar, Weekly report, Leave, Accounts.
6. **Refresh** — screenshots, pitch script, README.

