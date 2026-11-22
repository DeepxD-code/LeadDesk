"""Login, sessions and role checks."""
import hashlib
import hmac
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .db import ex, now_s, q, q1

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE = "leaddesk_session"

ROLE_LABELS = {
    "lead": "Team Lead",
    "member": "Team Member",
    "admin": "Administrator",
    "hr": "HR / Recruiter",
    "interviewer": "Interviewer",
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


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE) or request.headers.get("X-Session")
    if not token:
        raise HTTPException(401, "Please sign in")
    u = q1("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND u.active=1", (token,))
    if not u:
        raise HTTPException(401, "Please sign in")
    return u


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
def login(body: LoginIn, response: Response):
    u = q1("SELECT * FROM users WHERE username=? AND active=1", (body.username.strip().lower(),))
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(401, "Wrong username or password")
    token = secrets.token_urlsafe(32)
    ex("INSERT INTO sessions(token, user_id, created_at) VALUES (?,?,?)", (token, u["id"], now_s()))
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 12)
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


@router.get("/demo-users")
def demo_users():
    """Sign-in helper for the demo build: lists one account per role (no passwords)."""
    if os.environ.get("DEMO_MODE", "1") != "1":
        return {"users": []}
    picks = ["lead", "m01", "m02", "admin", "hr1", "hr2", "int1", "int2"]
    rows = q(f"SELECT * FROM users WHERE username IN ({','.join('?' * len(picks))})", picks)
    rows.sort(key=lambda r: picks.index(r["username"]))
    return {"users": [public_user(r) for r in rows]}
