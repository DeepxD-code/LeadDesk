# LeadDesk — one-page user guide

*A plain-language guide for team leads and team members. No training needed.*

---

## Signing in

1. Open **http://localhost:8000** in any browser.
2. On the sign-in screen, click the role you want to look at, then press **Sign in**. The demo password is already filled in.
3. To switch users, click your name in the top-right corner and choose **Sign out**.

---

## For team leads

### Seeing the team's work
Click **Board** in the left menu. Every task is a card in a column: *Pending*, *In progress*, *Done* or *Escalated*.

- **To move a task**, drag its card into another column, or click the card and change the status in the panel that opens.
- Every change is recorded. Open a card and click **History** to see who changed what, and when.
- A red stripe down the left of a card means the deadline has passed. An orange stripe means it is due today.

### Finding out who needs help
Click **Workload**. You get one row per person showing how many open tasks they hold, how many are overdue and how many are due today.

- The bar turns **red** when someone is over the limit, **orange** when they are close.
- The limit is set by the number near the top of the page. Change it and press **Save** — the colours update. The default is 6 open tasks per person.
- Press **Workload report** to download the same table as an Excel file.

### Handing out new work
Click **Board**, then **New task**. Fill in the title, who it is for, the deadline and the priority. Leave the person blank to keep it unassigned for later.

### Asking the SOPs a question
Click **Ask the SOPs** and type your question the way you would say it out loud — *"What do I do when error 402 appears?"*

- The answer is written for you, with the **document and section** it came from shown underneath. Click the source to read the exact lines.
- The assistant only answers from the documents your lead uploaded. If the answer is not in them, it says so plainly instead of guessing.

### The "Needs lead" list
Click **Needs lead**. These are the questions the SOPs could not answer. Each one is a gap in the documents.

- Type the answer and press **Send answer**. The person who asked is notified.
- If it belongs in an SOP, add it to the document — it will then be answered automatically next time.

### Adding or replacing SOP documents
Click **SOP documents**, then **Upload**. PDF and Word files are both accepted. The app reads the file, splits it by heading and makes it searchable in a few seconds.

---

## For team members

Click **My tasks** to see your own queue. Each task shows its deadline and a button to start it or mark it done. **Ask the SOPs** is the same assistant the lead uses.

---

## The HR document vault

Click **Document vault** (HR and administrators only; everyone else sees only their own documents).

- **Find a document:** type in the search box. This searches *inside* scanned pages too, so a photographed ID proof is found by its contents. Matching words are highlighted.
- **Change a document's type:** open it and pick the right type from the dropdown. The app suggests a type, but you always have the last word.
- **See what is actually stored:** open a document and press **Show the stored file**. You will see scrambled bytes, not a readable PDF — that is the encryption working.
- **Audit log:** every upload, view, download and search is listed with the person and the time. It cannot be edited or deleted, by anyone.

---

## Booking an interview

### As an interviewer
Click **My availability** and add the times you are free — a day, a start and end time, and how long each interview should be (30, 45 or 60 minutes). Press **Save**. These times appear on candidates' booking links and disappear as soon as someone takes them.

### As a recruiter
Click **Interviews**, then **Create booking link**. Choose the candidate and the round, then send the candidate their link. The page shows who has not booked yet.

### As a candidate
Open the link in the email — no account or password. Click the time that suits you and press **Book this time**, then **Confirm booking**. You will get a confirmation email with a calendar file attached; open it and the interview appears in your calendar. You can move or cancel the interview from the same link at any time.

### Recording feedback
After the interview, click **My interviews** and open the finished interview. Rate four things from 1 to 5, choose *Advance*, *Hold* or *Reject*, and write a few lines. **You cannot see anyone else's feedback until you have submitted your own** — so your opinion is your own.

---

## If something looks wrong

- **"Ollama not reachable"** — the local AI is not running. The assistant still works, quoting the best matching SOP section word for word. To turn the full assistant on, start Ollama and run `ollama pull qwen2.5:3b`.
- **A question was answered badly** — press the 👎 under the answer. It goes to the lead for correction, which is faster than emailing.
- **Signed out on its own** — sessions last 12 hours. Sign in again.
