# LeadDesk deployment

Three ways to run it, in order of how much you have to think.

| Path | Use it for | Time | HTTPS | Persistence |
|---|---|---|---|---|
| **A. Laptop, docker compose** | the demo, a judge's machine, a recording | 3 minutes | no | `./data` and `./secrets` on disk |
| **B. One VPS + Caddy** | a public URL you control | 20 minutes | automatic | same two folders, plus backups |
| **C. Managed host** | a quick throwaway URL | 10 minutes | provided | needs an attached disk |

The application is one container, one SQLite file and one key file. There is no
Redis, no queue, no external API. That is what makes deploy simple, and it is also
the constraint: **run exactly one worker**, and back up `data/` and `secrets/` as a
pair.

## Public team preview

The static preview at [leaddesk-preview.vercel.app](https://leaddesk-preview.vercel.app/)
is for sharing the interface with teammates. It uses synthetic data and simulates
actions in the browser; it has no backend, real sign-in, persistent storage, outbound
email, or real file uploads. Refreshing resets the sample records.

Use the Docker or persistent-host paths below for real work. The Vercel preview is not
a production deployment of the LeadDesk application.

---

## Before anything: the one switch that matters

`DEMO_MODE=1` shows one-click sign-in buttons on the login page and returns the demo
password, including the administrator's, from `GET /api/auth/demo-users`.

Set `DEMO_MODE=0` before the app is reachable from anywhere but your own machine.
The app logs a loud warning at startup if `DEMO_MODE=1` and `PUBLIC_BASE_URL` is not
a localhost address.

With `DEMO_MODE=0` the login form still works; you just need real passwords, which
is the next section.

### Set real passwords

There is a page (the **Password** button in the top bar) and a command:

```bash
# inside the container
docker compose exec app python scripts/reset_password.py admin 'a-long-new-password'
docker compose exec app python scripts/reset_password.py lead  'another-long-one'
```

Rules: at least 8 characters, and it refuses the demo password, `password`, `12345678`
and similar. The command signs out every existing session for that user.

---

## Path A: laptop demo

Prerequisites: Docker Desktop. Nothing else is required; the AI is optional.

```bash
docker compose up --build
```

| URL | What it is |
|---|---|
| http://localhost:8000 | LeadDesk |
| http://localhost:8025 | Mailpit: every invite, reminder and cancellation |
| http://localhost:11434 | Ollama, only if you run it on the host |

First start seeds the team, the SOPs, the vault documents and a week of question
history. It takes about 20 seconds.

Optional, and worth doing for a recording:

```bash
ollama pull qwen2.5:3b     # once
```

Without it the assistant still answers, in extractive mode: it quotes the best SOP
section and says so. The eval still scores 10/10, which is the point of the fallback.

Stop with `Ctrl+C`; remove everything including data with `docker compose down -v`
then delete `data/` and `secrets/`.

---

## Path B: one VPS with automatic HTTPS

Assumes a Linux host with Docker, a domain, and ports 80 and 443 open.

1. **DNS**: point `leaddesk.example.com` at the server's IP.

2. **Get the code** onto the server and enter the directory.

3. **Write `.env`** next to `docker-compose.yml`:

```env
DOMAIN=leaddesk.example.com
PUBLIC_BASE_URL=https://leaddesk.example.com
DEMO_MODE=0
SEED_DEMO=1
# real mail, so invites actually arrive
SMTP_HOST=smtp.yourprovider.com
SMTP_PORT=587
MAIL_FROM=LeadDesk <scheduler@leaddesk.example.com>
# optional, only if the model runs on this host
OLLAMA_URL=http://host.docker.internal:11434
LLM_MODEL=qwen2.5:3b
```

If your mail provider needs credentials, add them where `app/mailer.py` reads them, or
leave `SMTP_DISABLED=1` and use the outbox: nothing is lost, mail is queued and listed.

4. **Start** with the production compose file, which drops Mailpit, binds the app to
   localhost only, and puts Caddy in front:

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Caddy obtains and renews the certificate on its own. First request takes a few seconds.

5. **Set the passwords** (see above) and sign in.

6. **Verify**:

```bash
curl -fsS https://leaddesk.example.com/api/health
docker compose -f deploy/docker-compose.prod.yml ps
docker compose -f deploy/docker-compose.prod.yml logs --tail=50 app
```

You should see the startup line `LeadDesk ready. Time zone: Asia/Kolkata` and **no**
`DEMO_MODE is on` warning.

### Backups

`data/` holds `leaddesk.db` and the encrypted blobs. `secrets/` holds the vault master
key. **They are useless apart**: a database without its key is ciphertext, and a key
without the database is nothing.

```bash
# nightly, keep 14 days
docker compose -f deploy/docker-compose.prod.yml exec -T app \
  python -c "import sqlite3,shutil;shutil.copyfile('/app/data/leaddesk.db','/app/data/backup.db')"
tar czf /root/leaddesk-$(date +%F).tar.gz data/backup.db data/blobs secrets/ 2>/dev/null || \
tar czf /root/leaddesk-$(date +%F).tar.gz data secrets
find /root -name 'leaddesk-*.tar.gz' -mtime +14 -delete
```

Restore: stop the stack, unpack the archive over `data/` and `secrets/`, start again.

### Updating

```bash
git pull
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

The database is migrated in place at startup; `data/` is untouched by the rebuild.

## Google Calendar (optional)

Each interviewer can connect their own primary calendar from **My availability**.
LeadDesk checks free/busy periods before showing slots to candidates, then creates,
updates, or cancels the interview event and sends the calendar invitation from Google.
If Calendar is not connected, the existing email and `.ics` flow continues to work.
Google Calendar errors are shown to HR with a retry action; a confirmed booking is not
discarded when a calendar request fails.

To configure the connector:

1. In Google Cloud, enable the Google Calendar API and create an OAuth client for a
   web application.
2. Add the exact callback URL `https://<your-host>/api/iv/google/callback` to the
   OAuth client's authorized redirect URIs. For local Docker, use
   `http://localhost:8000/api/iv/google/callback`.
   Use an internal consent screen for your Workspace organization when available;
   otherwise add test users and follow Google's verification requirements.
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` in the
   server's `.env`, then restart the app. Do not commit the client secret.
4. Each interviewer signs in and selects **Connect Google Calendar**. Google displays
   the requested free/busy and owned-calendar event permissions before granting access.

OAuth tokens are encrypted with the vault master key. Back up `data/` and `secrets/`
together, and keep the key file outside Git. Disconnecting stops future synchronization;
events already created remain on Google Calendar. Internal interview notes are visible
only to HR and the assigned interviewer, and are not exposed to candidates.

### Firewall

Only 80 and 443 should be reachable. The app container binds to `127.0.0.1:8000` in the
production compose file, so even if the firewall is wrong, the app is not directly
exposed.

```bash
ufw allow 22,80,443/tcp && ufw enable
```

---

## Path C: a managed host (Render, Railway, Fly and similar)

The app is a normal container listening on `8000` and reading two filesystem paths.
What such platforms need you to do:

1. Deploy from the repository using the existing `Dockerfile`.
2. **Attach a persistent disk** and set `DATA_DIR` to a folder on it (for example
   `/var/data`) and `VAULT_MASTER_KEY_FILE=/var/data/secrets/vault_master.key`.
   Without a disk, every restart wipes the team, the SOPs and the vault key.
3. Set the environment: `PUBLIC_BASE_URL=https://<your-url>`, `DEMO_MODE=0`.
4. Keep **one instance**. Two instances mean two schedulers and duplicate reminders,
   and SQLite is a single file.
5. Ollama is not available on these platforms. Leave `OLLAMA_URL` unset: the assistant
   runs in extractive mode and the eval still passes 10/10. If you want the model,
   host it separately and point `OLLAMA_URL` at it.

---

## Environment reference

| Variable | Default | What it does |
|---|---|---|
| `DATA_DIR` | `./data` | SQLite database and encrypted blobs |
| `VAULT_MASTER_KEY_FILE` | `./secrets/vault_master.key` | where the vault key lives |
| `VAULT_MASTER_KEY` | unset | key inline as base64, instead of a file |
| `VAULT_AUTOCREATE_KEY` | `1` in Docker | generate the key on first run |
| `SEED_DEMO` | `1` | create the demo team, SOPs and history on an empty database |
| `DEMO_MODE` | `1` | one-click sign-in and the demo password endpoint. **Set to 0 in public** |
| `DEMO_PASSWORD` | `demo1234` | the password those buttons use |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | base of booking links in email; `https://` also enables Secure cookies |
| `GOOGLE_CLIENT_ID` | unset | OAuth web client ID for optional Calendar sync |
| `GOOGLE_CLIENT_SECRET` | unset | OAuth web client secret; keep it outside Git |
| `GOOGLE_REDIRECT_URI` | `<PUBLIC_BASE_URL>/api/iv/google/callback` | exact OAuth callback registered with Google |
| `OLLAMA_URL` | `http://localhost:11434` | local model endpoint |
| `LLM_MODEL` | `qwen2.5:3b` | model name |
| `LLM_TIMEOUT` | `120` | seconds before falling back to extractive mode |
| `SMTP_HOST`, `SMTP_PORT`, `MAIL_FROM` | Mailpit in compose | outbound mail |
| `SMTP_DISABLED` | unset | `1` queues mail in the outbox only |
| `SESSION_HOURS` | `12` | server-side session lifetime |
| `LOGIN_MAX_FAILURES` | `5` | failed logins before a lockout |
| `LOGIN_LOCK_SECONDS` | `60` | lockout length |
| `COOKIE_SECURE` | auto | force the Secure cookie flag |
| `MIN_PASSWORD_LENGTH` | `8` | password rule for the change form and the CLI |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` | something else on 8000 | `docker compose down`, or change the host port in the compose file |
| Login page shows no demo accounts | `DEMO_MODE=0` | that is correct in production; sign in with a real account |
| Assistant says "AI offline, quoting SOP sections" | Ollama not reachable | `ollama serve`, then `docker compose restart app`. Everything else still works |
| Hindi or Gujarati question answered with an English quote | model offline | expected; the lexicon retrieved the right section and the UI says it is quoting |
| `Permission denied` reading `secrets/` | container user cannot read the key | check the volume mount and file ownership |
| Vault documents show as unreadable | master key changed or lost | restore `secrets/` from backup with the matching `data/` |
| Reminders sent twice | more than one app instance or worker | run one |
| Mail never arrives | Mailpit in use, or SMTP blocked | read the outbox table, set real `SMTP_*`, open the port |
| `401 Your session has expired` | server-side expiry (12h) | sign in again; raise `SESSION_HOURS` if too short |
| `429 Too many failed attempts` | login throttle | wait 60 seconds |

---

## Pre-flight checklist for demo day

- [ ] `docker compose up --build` from a clean checkout works
- [ ] login page loads, "Take the 3-minute demo" signs you in as the lead
- [ ] **Judge demo** runs all five steps without an error
- [ ] **How we know it works** shows 5/5, 3/3, 2/2
- [ ] one Hindi question answers with an English source
- [ ] the booking page opens from an invite link and the `.ics` downloads
- [ ] the machine is on mains power, notifications muted
- [ ] a screen recording of a good run exists as a fallback

## Security checklist for a public URL

- [ ] `DEMO_MODE=0`
- [ ] every account has a real password (`scripts/reset_password.py`)
- [ ] `PUBLIC_BASE_URL` starts with `https://`
- [ ] `secrets/` is not readable by other users on the host
- [ ] firewall allows only 22, 80 and 443
- [ ] `data/` and `secrets/` are backed up together, off the machine
- [ ] `curl -I https://your-url` shows `content-security-policy`, `x-frame-options` and
      `strict-transport-security`
- [ ] one instance only
