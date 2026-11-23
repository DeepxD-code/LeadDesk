# Security walkthrough — for the judge

A live, ordered tour of the security story. Each control names the file and the endpoint or code path where it lives, so the
demo can be walked without improvising. The honest version of this story is the one in `SECURITY_NOTE.md`; this page is the
script for telling it.

---

## 1. Transport and response headers — `app/security.py`

Added by the `install()` middleware, on **every** response:

| Header | Value | Stops |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | MIME sniffing into executable types |
| `X-Frame-Options` | `DENY` | clickjacking |
| `Referrer-Policy` | `no-referrer` | referrer leakage |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=(), payment=()` | unused device access |
| `Cross-Origin-Opener-Policy` | `same-origin` | cross-origin window leakage |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'` | injection/clickthrough into the page itself |

The booking page (`/book/...`) is one self-contained file with inline style and script, so it gets `script-src 'self' 'unsafe-inline'`;
every other page ships code as a separate file and gets the strict form.

**HSTS** is only sent when the scheme is `https` or `x-forwarded-proto` is `https`: `Strict-Transport-Security: max-age=31536000; includeSubDomains`.

**Live check:**
```bash
curl -I http://localhost:8000/api/health
# expect: x-content-type-options: nosniff, x-frame-options: DENY, content-security-policy: <the policy above>
```

## 2. Login brake — `app/security.py` (`/api/auth/login`)

- `LOGIN_MAX_FAILURES` (default **5**) failed attempts before lockout; `LOGIN_LOCK_SECONDS` (default **60**) lockout length.
- Repeated failures return `429` and lock the account; the lock is server-side state, not client-side.

**Live check:** fail five times against one account, expect `429` / lockout message.

## 3. Sessions — `app/auth.py` + `app/security.py`

- Cookie `leaddesk_session`: `httponly`, `samesite=lax`, `secure` when the request is https or `COOKIE_SECURE`/`PUBLIC_BASE_URL` says so.
- **Server-side expiry**: sessions are time-limited (`SESSION_HOURS`, default **12**) in the sessions table; the app returns `401 Your session has expired` when the row is stale.

**Live check:** sign in, wait/expire server-side, expect the 401 rather than a silent pass.

## 4. Demo guard — `app/main.py` (`_warn_if_public_demo`)

- `DEMO_MODE=1` is the default and signs anyone in as the admin; the startup log warns loudly when `PUBLIC_BASE_URL` is public.
- `DEMO_MODE=0` + real passwords is the only acceptable public posture (see `DEPLOY.md`).

## 5. Uploads — `app/sop.py`, `app/vault.py` + `app/security.py:check_magic`

- SOP uploads: 25 MB cap, read with `limit + 1` (reject before buffering), magic bytes checked (`%PDF` for pdf, zip `PK` for docx), name sanitized with `os.path.basename`.
- Vault uploads: 20 MB cap, read with `limit + 1`, magic bytes checked.

A file whose bytes do not match its declared type is rejected with `400 File content does not match the declared type ...`.

## 6. Vault encryption and audit — `app/crypto.py`, `app/vault.py`

- Envelope encryption: per-file random 256-bit data key, sealed with the master key; file + text sealed with the data key; `LDV1` marker on stored blobs.
- Forced key rotation on re-upload via content hash (`sha256`).
- Audit log: hash-chained rows (`prev_hash` → `hash`) with SQLite triggers preventing update/delete of history; denied access attempts are recorded as first-class events.

## 7. Access control and delete approval — `app/vault.py`, role deps

- One role per scope, checked server-side on every endpoint: `member` (own `employee_id`), `hr` (own department), `admin` (all + approvals), `lead` (own documents).
- Search is scoped the same way; denials are audited.
- Deletion requires **two-person approval**, enforced server-side: approver must differ from requester, second approver (admin) required.

## 8. What the AI answers from — `app/sop.py`

Answers come only from indexed SOP chunks; otherwise the assistant returns `NOT_IN_SOP` rather than guessing.

---

## Demo script order (walk this live)

1. **Headers**: `curl -I` → nosniff/DENY/CSP present; over `https` also see HSTS.
2. **Login brake**: five bad attempts → `429` + lockout.
3. **Session**: sign in → use → expect `401` after server-side expiry (or shorten `SESSION_HOURS` in a demo run).
4. **Upload gate**: try a mismatched file (e.g. a text file renamed `.pdf`) → `400`; try an oversized file → `400` before buffering.
5. **Vault**: upload a sample → confirm `LDV1` ciphertext marker; open "How we know it works" → audit chain verifies.
6. **Delete approval**: request delete → second approver must approve; requester cannot self-approve.

Keep the whole walkthrough under ~3 minutes. Any control that needs an external dependency (TLS termination, KMS, ClamAV, off-box log shipping) is named in `SECURITY_NOTE.md` as production-only.
