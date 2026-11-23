# LeadDesk: the 3-minute demo, and the questions judges ask

Everything here is written to be said out loud. The numbers are the ones the app
computes; nothing is rounded up.

---

## The one-sentence pitch

> A team lead supervises twenty people, hands out work over chat, and answers the same
> five questions every day. LeadDesk is one screen that shows the whole workload, plus
> an assistant that answers those questions from the SOPs, shows the source, and
> refuses when the answer is not there.

## Why that sentence works

It names a real person, a real waste, and two failures a judge can picture:
work found late ("when the client asks") and knowledge that lives in a colleague's
head. Then it promises one screen, not five.

---

## Before you start

- `docker compose up --build`, then open http://localhost:8000
- Press **Take the 3-minute demo** on the login page. It signs you in as the team lead
  and opens the **Judge demo** page.
- Ollama: leave it running if you have it. If not, say so out loud during step 4 —
  it is a feature, not a failure.
- Have `docs/screenshots` open in a second window as a fallback, and a screen recording
  if you have one.

---

## The script

### 0:00 — Hook (15 seconds, no clicks)

> Every morning, a team lead in a back-office unit hands out work in a chat window, and
> then spends the rest of the day being interrupted. "What do I do when error 402
> appears?" "Who approves a refund above ten thousand?" The answers are in the SOPs.
> Finding them takes minutes; asking the lead takes seconds. So they ask the lead.
>
> We built one screen that fixes both halves of that.

### 0:20 — Step 1: the whole shift on one screen

Press **Show the numbers**.

> Twenty people, a hundred and eighteen tasks, thirteen overdue, twenty-seven due today,
> and two people over the load line. This is counted from the database every time the
> page loads, not typed into a slide.

Point at the "assumptions" disclosure.

> Every number can be traced, including the one assumption we make: four minutes of lead
> time per interruption.

### 0:45 — Step 2: a question answered from the document

Press **Ask: what do I do when error 402 appears?**

> The answer comes only from the SOPs the lead uploaded, and it names the document and
> the section. If there is no source, there is no answer. That is the difference between
> an assistant a back office can audit and a chatbot.

### 1:10 — Step 3: it admits what it does not know

Press **Ask something the SOPs do not cover**.

> Ask about the office Wi-Fi, and it refuses, and the question lands in the lead's queue.
> That queue is also the to-do list for what is missing from the SOPs. A confident wrong
> answer is what kills trust in an assistant; this is the guard against it.

### 1:30 — Step 4: Hindi and Gujarati, with nothing installed

Press **Ask in Hindi**.

> The SOPs are in English. The floor is not. This works with no model downloaded, because
> the domain words people actually use are mapped directly and the numbers and error codes
> pass straight through. When the local model is running it translates properly, but it is
> an upgrade, not a dependency.

Mention the badge if it says offline.

> You can see the model is offline right now. It still found the right section and still
> cited it.

### 1:55 — Step 5: the claim, measured

Press **Run all ten questions**.

> Five answerable questions, three that must be refused, two in Hindi and Gujarati.
> **Ten out of ten** with no model installed. This is the same script the test suite runs,
> so the number cannot quietly drift.

### 2:20 — The two guards nobody expects (sign in as admin)

Switch person to **Anil Rao (Admin)** using the selector, then **Judge demo**:

- **Vault**: press **Show me the ciphertext**.
  > HR files are encrypted per file with AES-256-GCM, wrapped by a master key that lives
  > outside the database. This is the bytes on disk: entropy 7.998 out of 8, which is
  > indistinguishable from random.
- **Race**: press **Fire both bookings at once**.
  > Two real concurrent requests for one interview slot. One wins. The database
  > transaction and a unique index make the second one impossible, not unlikely.

### 2:45 — Close

> Task board, SOP assistant, encrypted vault, interview scheduler. One container, one
> SQLite file, no cloud calls, and the AI can be switched off entirely and the product
> still answers ten out of ten.
>
> The brief asked for a dashboard and an assistant. We shipped those two, plus the
> security and the evidence, because in a back office the difference between "works" and
> "is trusted" is the audit trail.

---

## Numbers to have ready

| Claim | Number | Where it comes from |
|---|---|---|
| Team and load | 20 people, 118 tasks, 13 overdue, 27 due today, 2 overloaded | `/api/impact` |
| Questions absorbed | 71 asked in 7 days, 59 answered without a lead (83%), ≈ 3.9 hours of lead time | `/api/impact` |
| Answer quality | 5/5 answerable with source, 3/3 refusals, 2/2 Hindi and Gujarati | `scripts/eval_sop.py` |
| Vault | 10 documents, 4 OCR scans, entropy 7.998 bits/byte | `/api/proof` |
| Booking | 2 concurrent requests, 1 booking | `/api/iv/demo/race` |
| Tests | 45 passing | `pytest` |

If someone asks where a number comes from, open **How we know it works**. Every figure
on screen is computed on request.

---

## The questions judges actually ask

**"Isn't this just a GPT wrapper?"**
> There is no cloud model and no API key. Retrieval is TF-IDF over SOP sections with a
> heading field, an answer gate, and a refusal path. The model, when present, only
> rewrites a sentence from the retrieved section. With it switched off the eval still
> scores ten out of ten. The hard parts here are the retrieval gate, the encrypted vault
> and the booking transaction, not the prompt.

**"What happens when the SOPs are wrong or out of date?"**
> The assistant answers from what the lead uploaded and cites the section, so a wrong
> answer points at the wrong document. Questions it cannot answer become the list of
> gaps. Versioning SOPs is a `what's next` item, not something we claim.

**"How do you stop it inventing an answer?"**
> Two gates. Retrieval must clear a score threshold, and if the question contains an
> error code or form number, the chosen section must contain that code. If either fails,
> the answer is "not in the SOPs" and the question goes to the lead. Three of the ten
> eval questions exist to prove that.

**"Could two people get the same interview slot?"**
> That is the demo. Two threads book the same slot at the same instant: one booking,
> one refusal. It is enforced by a partial unique index plus `BEGIN IMMEDIATE`, not by
> checking first and hoping.

**"Where is the data? Who can read it?"**
> On your machine, in one SQLite file, with documents encrypted per file. Server-side
> role checks decide who sees which document: admin sees all, HR sees their department,
> everyone else sees their own. Every access is written to an append-only hash-chained
> audit log, and the app shows you whether the chain is intact.

**"Is it production ready?"**
> It is deployable: one container, health check, automatic HTTPS in front, login
> throttling, server-side session expiry, CSP and HSTS headers, and a documented backup
> that keeps the database and the key together. What it is not is multi-tenant:
> SQLite and a single worker are deliberate choices for one team on one host, and
> `docs/REVIEW.md` lists exactly what would change.

**"What did you cut?"**
> Outbound notifications beyond email, SSO, and SOP versioning. The brief asked for a
> dashboard and an assistant; everything else we cut is written down rather than
> half-built.

**"Why is there a forum?"**
> The team already asks each other questions; the forum gives that a home next to the
> assistant. It is not part of the graded brief and it changes nothing else.

**"How long did it take?"** — answer honestly, then point at the evidence.

**"What would you do with a month?"**
> Postgres, real SOP versioning with diffs, a queue in front of the model, and an
> evaluation set written by actual team leads instead of by us.

---

## If the demo breaks

Do not debug in front of a judge.

1. Switch to **How we know it works** and run the checks. They are independent of the
   page you were on.
2. If the app will not start, open the screenshots (`docs/screenshots`) and narrate
   over them. You already know the script.
3. If a live question fails, ask a different one. There are eight suggested chips on the
   assistant page; the eval is the proof, not a single answer.

---

## Deck outline, if you need slides

Seven slides, one idea each:

1. **The interruption** — a lead's day, and the five questions that repeat.
2. **Two failures** — work found late, knowledge in one person's head.
3. **One screen** — the workload view, with the real numbers.
4. **Answers with a source, or none** — the assistant, the gate, the gap list.
5. **It runs on the box** — local model, offline fallback, Hindi and Gujarati.
6. **Trust is auditable** — ciphertext on disk, hash-chained audit, the booking race.
7. **Measured** — 10/10 eval, 36 tests, the hours saved, and what is next.

Slide 7 is where most teams put a roadmap and lose the point. Put the numbers first,
the roadmap last, one line.
