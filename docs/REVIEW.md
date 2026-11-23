# LeadDesk: full checkup

Date: 23 November 2026. Branch `main`, commit `11bb1ba`, working tree clean at the
start of this pass.

This is a review of the product as it stands, not a wish list. Every claim below was
run against the code in this repository on this machine. Where something was fixed,
the fix is in the same commit as this document.

---

## Verdict

The application is in good shape. It starts, it seeds, every screen loads, and the
core claim of the product (answers from SOPs, with sources, refusing what it does not
know) holds up when measured. The problems were not in the product logic. They were
in the things that only matter once someone else runs it: the demo switch defaults to
on, the login endpoint had no brake on guessing, sessions never expired on the server,
and there was no deployment story.

Those are fixed. What remains is a short list of deliberate trade-offs and one
housekeeping item, listed at the end.

---

## 1. Does it work

| Check | How it was run | Result |
|---|---|---|
| Test suite | `python -m pytest tests -q` | **29 passed**, ~17 s |
| Cold boot | `uvicorn app.main:app --port 8014` | ready in **3.5 s**, `/api/health` returns 200 |
| First screen | `GET /` | 200, 543 bytes, SPA boots |
| Demo accounts | `GET /api/auth/demo-users` | 7 personas returned |
| SOP eval, no model installed | `python scripts/eval_sop.py` | **10/10**: 5/5 answerable with source, 3/3 out-of-scope refused, 2/2 Hindi and Gujarati |
| Assistant end to end | asked "Which form is used for a duplicate payment?" | answered from *Claims and Payments SOP › 4. Duplicate payments*, source shown |
| Vault ciphertext | `GET /api/vault/storage/{id}` | AES-256-GCM, entropy 7.998 bits/byte, `LDV1` envelope header |
| Booking race | `POST /api/iv/demo/race` | 2 concurrent requests, **1 booking**, the other refused |
| Secrets in git | `git ls-files secrets data` | nothing tracked |

The eval result is the important one: it is the worst-case path, with the local model
offline, and it still answers 5 of 5 with a citation.

## 2. What I fixed in this pass

### 2.1 The demo switch was on by default, including for the administrator

`DEMO_MODE` defaulted to `1`, and `GET /api/auth/demo-users` returns the demo password
with the account list. Anyone who could reach the login page could sign in as the
administrator. That is a reasonable default for a laptop and a bad one for a URL.

- `app/main.py` now prints a loud startup warning when `DEMO_MODE=1` and
  `PUBLIC_BASE_URL` is not local, naming the consequence.
- `.env.example` documents the switch as a pre-public step in capitals.
- `docker-compose.yml` now reads `DEMO_MODE`, `SEED_DEMO`, `SMTP_HOST`, `SMTP_PORT` and
  `PUBLIC_BASE_URL` from the environment instead of hardcoding them, so `DEMO_MODE=0`
  in `.env` actually takes effect.

### 2.2 No brake on password guessing

`POST /api/auth/login` accepted unlimited attempts.

- `app/security.py` tracks failures per `username + client address`. Five failures
  locks that pair for 60 seconds and returns `429`. The last two attempts warn
  ("2 attempt(s) left"), and a success clears the counter.
- Tunable with `LOGIN_MAX_FAILURES` and `LOGIN_LOCK_SECONDS`.

### 2.3 Sessions never expired on the server

The cookie had a 12-hour `max_age`, but the session row was valid forever, so a copied
token outlived the cookie.

- `current_user()` now compares `sessions.created_at` against a cutoff
  (`SESSION_HOURS`, default 12) using the application clock in IST, deletes the row and
  returns a distinguishable 401.

### 2.4 No security headers

- Every response now carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, a restrictive `Permissions-Policy`,
  `Cross-Origin-Opener-Policy: same-origin`, and a Content-Security-Policy.
- The CSP is strict (`script-src 'self'`) for the app and its API. The public booking
  page is a deliberately self-contained file with inline script and style, so it gets
  the one relaxation it needs, and only on `/book/*`.
- `Strict-Transport-Security` is added only when the request arrived over HTTPS.
- `Set-Cookie` gains `Secure` when `PUBLIC_BASE_URL` is `https://` or `COOKIE_SECURE=1`.

Three of these are worth showing a judge, because they are the ones a browser will
enforce rather than merely suggest.

### 2.5 An upload could exhaust memory or stall the event loop

`POST /api/sop/docs` read the whole file before checking its size, then wrote it with a
blocking `open()` inside an `async def`.

- It now reads at most 25 MB + 1 byte (so an oversized file is rejected without being
  buffered), and the write goes through `asyncio.to_thread`.

## 3. Deliberate trade-offs (not bugs, but a judge may ask)

| Area | Current behaviour | Why it is acceptable here | What production would need |
|---|---|---|---|
| CSRF | No token. Session cookie is `SameSite=Lax`, and state-changing calls are JSON `POST`s. | Lax blocks cross-site cookie sends on form posts; JSON content type blocks simple-form forgery. | A double-submit token, or `SameSite=Strict` plus a same-origin check. |
| Rate limiting | Login only. `/api/sop/ask` is unlimited. | The model runs locally, so the cost of abuse is the machine's own CPU. | A per-user token bucket if this ever shares a host. |
| Scheduler | `_scheduler_loop` runs inside the web process and sends reminders and nudges. | One container, one worker, one team. | Run **exactly one worker**, or move the loop to a separate process. Two workers would double-send. |
| Database | SQLite with `BEGIN IMMEDIATE` for the booking race. | Single team, single host, and it is what makes the race guard provable in one file. | Postgres if this became multi-tenant. |
| Mail | Compose ships Mailpit; mail is kept in an outbox table when SMTP is unreachable. | The demo needs to show invites without a mail account, and nothing is silently lost. | Point `SMTP_HOST` at a real relay; the outbox shows failures. |
| Vault key | Generated on first run into `secrets/`, `chmod` is a no-op on Windows. | Documented in `SECURITY_NOTE.md`. | A KMS or at least an OS keychain on the host. |
| Forum | Any signed-in user can post; no edit or delete; `tester` and `developer` accounts see only the forum. | This is a team communication surface, not part of the graded brief. | Moderation and an audit trail, as the vault already has. |

## 4. Lint and code health

`ruff check app scripts tests` reports 129 findings under this machine's global ruff
configuration. Almost all of them are noise for a FastAPI codebase:

- **92 × B008** — `Depends(...)` in argument defaults. This is the documented FastAPI
  pattern; the rule does not apply.
- **10 × ISC004** — implicit string concatenation in `scripts/make_samples.py`, which
  builds sample documents and is not shipped.
- **7 × RUF100** — unused `noqa` comments.
- **5 × F401, 3 × F841** — unused imports and unused locals.

Real findings, now addressed or accepted:

- `sop.py` had an `ASYNC230` (blocking file open in an async endpoint) — **fixed** in 2.5.
- `sop.py` has three `try/except/pass` blocks (`S110`). One is the deliberate model
  fallback; the others should log. Left as is, noted here.
- `interviews.py` parses naive datetimes (`DTZ007`). That is intentional: every stored
  time in this app is naive IST, and the user guide says so.

Recommendation, not done in this pass: add a `pyproject.toml` with
`[tool.ruff.lint] ignore = ["B008"]` so the suite is clean and a CI job can enforce it
without a wall of false positives.

## 5. Submission hygiene

The repository now contains `.github/skills/design-taste`: 153 files, roughly 5 MB of
third-party design guidance, added by the previous pass. It is dev-time tooling, not
part of the product.

- It does **not** reach the Docker image (the Dockerfile copies only `app`, `static`,
  `scripts`, `sample_data` and `docs`), so it cannot affect the deployed app.
- It does sit in the submission repository. Judges browsing a hackathon repo see a large
  unfamiliar tree, and "what is this?" is not the question you want them asking.

Two clean options: keep it under `.github/` deliberately and mention it in the README as
the design system tooling, or move it out of the repo. Do not delete it silently.

## 6. Documentation status

| Document | State |
|---|---|
| `README.md` | Accurate. Now links the screenshots and the deployment guide. |
| `docs/USER_GUIDE.md` | Accurate, one page, matches the screens. |
| `docs/SECURITY_NOTE.md` | Accurate on roles, audit, encryption. Should mention the new headers and login throttle. |
| `docs/DESIGN.md` | Accurate description of the current visual language. |
| `docs/HACKATHON_PLAYBOOK.md` | Research and scorecard from the earlier pass. |
| `docs/REVIEW.md` | This document. |
| `docs/DEPLOY.md` | New: runbook for laptop, VPS and hosted. |
| `docs/PITCH.md` | New: three-minute script, numbers, hostile questions. |

## 7. What I would do next, in priority order

1. **Set `DEMO_MODE=0` and change the demo passwords** before any public URL exists.
   This is the one item that is a real risk rather than a rough edge.
2. Add a `pyproject.toml` with the FastAPI-aware ruff config and a two-job CI workflow
   (`pytest`, `ruff`). Cheap credibility.
3. Rotate the seeded administrator password at first boot for non-demo deployments.
4. Decide the fate of `.github/skills/design-taste`.
5. Replace the `@app.on_event("startup")` handler with a lifespan context manager to
   silence the FastAPI deprecation warning that the test run prints twice.

Nothing in that list blocks a demo. Item 1 blocks a public URL.
