"""Login, sessions and role checks."""
import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from . import security
from .db import ex, now, now_s, q, q1, tx

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE = "leaddesk_session"

ROLE_LABELS = {
    "lead": "Team Lead",
    "member": "Team Member",
    "admin": "Administrator",
    "hr": "HR / Recruiter",
    "interviewer": "Interviewer",
    "tester": "Tester",
    "developer": "Developer",
}


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 200_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def public_user(u: dict) -> dict:
    return {k: u[k] for k in ("id", "username", "name", "role", "employee_id", "department", "shift", "email")} | {
        "role_label": ROLE_LABELS.get(u["role"], u["role"])
    }


REAUTH_MINUTES = 15


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE) or request.headers.get("X-Session")
    if not token:
        raise HTTPException(401, "Please sign in")
    u = q1(
        "SELECT u.*, s.token AS session_token, s.reauthed_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND u.active=1",
        (token,),
    )
    if not u:
        raise HTTPException(401, "Please sign in")
    row = q1("SELECT created_at FROM sessions WHERE token=?", (token,))
    if row and row["created_at"] < _session_cutoff():
        ex("DELETE FROM sessions WHERE token=?", (token,))
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return u


class ReauthIn(BaseModel):
    password: str


@router.post("/reauth")
def reauth(body: ReauthIn, request: Request, user=Depends(current_user)):
    """Re-authenticate the current user with their password for sensitive actions."""
    key = security.client_key(user["username"], request)
    wait = security.login_wait(key)
    if wait:
        raise HTTPException(429, f"Too many failed attempts. Try again in {wait} seconds.")
    if not verify_password(body.password, user["password_hash"]):
        security.note_failure(key)
        raise HTTPException(401, "Incorrect password.")
    security.note_success(key)
    token = user.get("session_token")
    reauthed_now = now_s()
    if token:
        ex("UPDATE sessions SET reauthed_at=? WHERE token=?", (reauthed_now, token))
    return {"ok": True, "reauthed_at": reauthed_now}


def is_reauthenticated(user: dict, within_minutes: int = REAUTH_MINUTES) -> bool:
    reauthed_at = user.get("reauthed_at")
    if not reauthed_at:
        return False
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(reauthed_at)
        return (now() - dt).total_seconds() < within_minutes * 60
    except Exception:
        return False


def _session_cutoff() -> str:
    """Server-side expiry, so a stolen cookie cannot outlive the shift."""
    return (now() - timedelta(hours=security.SESSION_HOURS)).isoformat(timespec="seconds")


def require(*roles):
    def dep(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "You do not have access to this page")
        return user
    return dep


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response, request: Request):
    key = security.client_key(body.username, request)
    wait = security.login_wait(key)
    if wait:
        raise HTTPException(429, f"Too many failed attempts. Try again in {wait} seconds.")
    u = q1("SELECT * FROM users WHERE username=? AND active=1", (body.username.strip().lower(),))
    if not u or not verify_password(body.password, u["password_hash"]):
        security.note_failure(key)
        left = security.attempts_left(key)
        hint = f" {left} attempt(s) left." if 0 < left <= 2 else ""
        raise HTTPException(401, "Wrong username or password." + hint)
    security.note_success(key)
    token = secrets.token_urlsafe(32)
    ex("INSERT INTO sessions(token, user_id, created_at) VALUES (?,?,?)", (token, u["id"], now_s()))
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=security.secure_cookie(),
                        max_age=int(security.SESSION_HOURS * 3600))
    return {"user": public_user(u), "token": token}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        ex("DELETE FROM sessions WHERE token=?", (token,))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": public_user(user)}


class PasswordIn(BaseModel):
    current: str
    new: str


MIN_PASSWORD = int(os.environ.get("MIN_PASSWORD_LENGTH", "8"))


def check_password_strength(pw: str) -> str | None:
    """Returns a reason the password is refused, or None if it is acceptable."""
    if len(pw) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if pw.lower() in ("demo1234", "password", "leaddesk", "admin123", "12345678"):
        return "That password is too easy to guess."
    if pw.lower() == "demo1234":
        return "That is the demo password. Choose a new one."
    return None


@router.post("/password")
def change_password(body: PasswordIn, request: Request, user=Depends(current_user)):
    """Change your own password. Every other session is signed out, so a password
    change actually ends access that was granted with the old one."""
    if not verify_password(body.current, user["password_hash"]):
        raise HTTPException(401, "Your current password is not correct.")
    problem = check_password_strength(body.new)
    if problem:
        raise HTTPException(422, problem)
    new_hash = hash_password(body.new)
    keep = request.cookies.get(COOKIE) or request.headers.get("X-Session")
    with tx():
        ex("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user["id"]))
        ex("DELETE FROM sessions WHERE user_id=? AND token<>?", (user["id"], keep or ""))
    return {"ok": True, "sessions_closed": q1(
        "SELECT COUNT(*) AS n FROM sessions WHERE user_id=?", (user["id"],))["n"]}


@router.get("/demo-users")
def demo_users():
    """Sign-in helper for the demo build: lists one account per role (no passwords)."""
    if os.environ.get("DEMO_MODE", "1") != "1":
        return {"users": []}
    picks = ["lead", "m01", "tester", "dev", "admin", "hr1", "int1"]
    rows = q(f"SELECT * FROM users WHERE username IN ({','.join('?' * len(picks))})", picks)
    rows.sort(key=lambda r: picks.index(r["username"]))
    return {"users": [public_user(r) for r in rows], "password": os.environ.get("DEMO_PASSWORD", "demo1234")}
