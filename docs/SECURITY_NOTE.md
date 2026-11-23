# Security note — HR document vault

This states plainly what is protected, what is not, and what production would need next.

---

## What is encrypted

| Thing | How |
|---|---|
| Document contents on disk | AES-256-GCM, encrypted **before** anything is written to the filesystem |
| Extracted and OCR text | AES-256-GCM, same per-file key as the document |
| Per-file data key | Wrapped (encrypted) with the master key, stored beside the metadata |
| Transport (production) | Not handled by this app — put it behind HTTPS |

Encryption happens in `app/crypto.py`. Every uploaded file gets its **own** randomly generated 256-bit data key. The file
and its text are sealed with that key; the key itself is sealed with the master key and stored next to the record. This
is envelope encryption: a leaked metadata row reveals nothing, and one file's key cannot open another file.

Each blob on disk begins with the marker `LDV1` followed by a nonce and ciphertext. That marker is deliberate — it makes
it obvious at a glance that a stored file is **not** a readable PDF or JPEG. The vault page has a **Show the stored file**
button that prints these raw bytes next to the decrypted text, so the claim can be checked rather than believed.

## Where the keys are kept

- The **master key** is never in the source code and never in the database. It is read from `VAULT_MASTER_KEY` (base64)
  or from a file, `secrets/vault_master.key`, which is outside the application directory and outside git
  (`.gitignore` excludes `secrets/`, and `.dockerignore` keeps it out of the image).
- It is created on first run with `os.urandom(32)`, written with permissions `0600`, and a warning is logged.
- In Docker the key lives on its own volume (`./secrets:/app/secrets`), so it is not baked into the image and not
  carried in a container layer.
- File permissions are applied on Linux. **On Windows `os.chmod` has no real effect**, so the key file is protected only
  by the account that created it being the only account able to read the folder. Treat the host as trusted.

**Losing the master key means the documents are unrecoverable.** That is the intended behaviour, and it is also the one
thing to back up. Rotating the key requires decrypting and re-encrypting every file; no rotation feature is implemented.

## Access control

One role decides one scope, checked on the server for every request — the browser is never trusted:

| Role | Sees |
|---|---|
| `member` | documents matching their own `employee_id` |
| `hr` | documents in their own department |
| `admin` | everything, plus delete approvals and the ciphertext view |
| `lead` | their own documents only, under the same employee-ID rule as a member |

Search is scoped by the same rules, so a denied user cannot find a document by guessing words from it. A denied attempt
on a specific document is written to the audit log with outcome `denied`, which matters: the failed attempt is evidence.
Note the distinction — a **scope** denial (a document that exists but is outside your role) is audited; a plain
**role-gate** refusal (a page your role may not open at all) returns `403` and is not audited, since nothing in the vault
was touched.

Task history follows the task-board boundary too: leads and admins can view any history; members can view only tasks
assigned to them. HR and interviewer roles are denied.

Demonstrating a denial is built in: sign in as `hr1` and open a document belonging to another department, or search for a
phrase that exists only in that document. Both return nothing, and both appear in the audit log as denied.

## The audit log

Every upload, view, download, search and denied attempt records the user, their role, the time, the document and the
outcome. Two independent protections stop it being covered up:

1. SQLite triggers `audit_no_update` and `audit_no_delete` abort any `UPDATE` or `DELETE` on the table. This holds even
   for an attacker who has the database file and connects directly — it is enforced by the engine, not by the app.
2. Each row stores `prev_hash` and `hash`, forming a hash chain. Editing an old row would break every hash after it.
   **How we know it works** shows a live chain verification, and `vault.verify_chain()` recomputes it.

A determined attacker with write access to the SQLite file could drop the triggers and rewrite the chain. That is why
production needs the log shipped off-box (see below).

## What is **not** protected

Worth stating directly:

- **A compromised host ends everything.** This is a single-machine deployment. Anyone who can read the process memory,
  the SQLite file *and* the key file has both halves and can decrypt the vault. Encryption here protects against stolen
  disks and copied folders, not against root on the running server.
- **No HTTPS.** Traffic is plain HTTP, so a session cookie can be sniffed on an untrusted network. Fine for a demo on a
  local machine; unacceptable in production.
- **Sessions are bearer tokens with no expiry check at the server.** They are `httponly` cookies, cleared after 12 hours
  by the browser, but the session row itself is not time-limited server-side. There is no re-authentication for
  sensitive actions, no rate limiting on the login form, and no account lockout. (Superseded during the security pass of
  24 November 2026: server-side expiry, login throttling/lockout and the demo-account scope restriction are now in; the
  remaining production gap is re-authentication for download and delete.)
- **No CSRF tokens.** Cookies are `samesite=lax`, which blocks the classic cross-site form POST, but this is a browser
  behaviour relied on rather than an explicit control.
- **No virus scanning.** An uploaded file is encrypted and stored; its contents are not inspected for malware.
- **The extracted text lives in the database, encrypted, but is loaded into memory in the clear** while the app runs and
  while a search executes. Query strings are not written to logs by the app, but a search term is visible to whoever
  can read the process.
- **Backups are not encrypted by this app.** Whoever copies `data/` gets ciphertext, which is safe — unless they also
  copy `secrets/`. Keep the two apart.
- **Metadata is not encrypted.** Filenames, employee IDs, document types and upload dates are plaintext in the database,
  because the app needs to list and filter on them.

## What production would need

In rough priority order:

1. **TLS** with HSTS, and secure, `httponly`, `samesite=strict` cookies.
2. **A real key service** — AWS KMS, GCP KMS or HashiCorp Vault — so the master key never sits on the application host,
   plus a documented rotation procedure and re-encryption job.
3. **Ship the audit log off-box** to append-only storage (S3 Object Lock, an immutable log service) so a host compromise
   cannot rewrite history. Keep the hash chain as tamper evidence in transit.
4. **Server-side session expiry** and idle timeout, refresh-on-activity, and re-authentication for download and delete.
5. **Rate limiting and lockout** on login, and audit-driven alerting on repeated denials.
6. **Two-person approval for deletion**, which is already modelled (`vault_delete_requests`) and enforced server-side:
   the approver must differ from the requester, with a second approver required for the decision.
7. **Antivirus scanning** (ClamAV) on upload, and content-type validation by magic bytes rather than file extension.
8. **Field-level encryption or a separate metadata store** if filenames and employee IDs are themselves sensitive.

## Already implemented beyond the minimum

- Retention dates per document.
- Expired documents remain listed with an expiry marker, but content, file, ciphertext-proof and search access are
  denied; HR/admin can renew retention or request deletion.
- Watermarked downloads.
- Two-person approval for deletion.
- Hash-chained, append-only audit log with engine-level triggers.
- Denied attempts recorded as first-class audit events.
- Per-file key rotation on re-upload, forced by content hashing (`sha256`) on every document.
- Content-type validation by magic bytes rather than file extension, on both the SOP and vault uploads.
- Upload reads capped before buffering (20 MB vault / 25 MB SOP), so an oversized upload is rejected without ever being
  loaded into memory.
- Lint and test CI (`.github/workflows/ci.yml`): ruff (F/E9/W/I) plus the pytest suite, on push and pull request.

## Team forum and demo accounts

The team forum is available to every signed-in account. Forum posts and replies are visible to all forum users; it is
not a private-message system. The `tester` and `developer` demo roles are restricted server-side to forum and auth
endpoints. Demo accounts share `DEMO_PASSWORD`, which the demo persona helper returns while `DEMO_MODE=1`. Set both
`DEMO_MODE=0` and `SEED_DEMO=0` outside a local/demo environment.
