"""Authenticated team discussion forum."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .auth import ROLE_LABELS, current_user
from .db import ex, now_s, q, q1, tx

router = APIRouter(prefix="/api/forum", tags=["forum"])


class PostIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=5000)


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)


def _present(row):
    return {
        key: row[key]
        for key in ("id", "title", "body", "created_at", "updated_at", "reply_count", "author_name", "author_role")
        if key in row
    } | {"author_role_label": ROLE_LABELS.get(row["author_role"], row["author_role"])}


def _reply_present(row):
    return {
        "id": row["id"],
        "body": row["body"],
        "created_at": row["created_at"],
        "author_name": row["author_name"],
        "author_role": row["author_role"],
        "author_role_label": ROLE_LABELS.get(row["author_role"], row["author_role"]),
    }


@router.get("/posts")
def list_posts(user=Depends(current_user)):
    rows = q("""SELECT p.id, p.title, p.body, p.created_at, p.updated_at, u.name AS author_name, u.role AS author_role,
                       (SELECT COUNT(*) FROM forum_replies r WHERE r.post_id=p.id) AS reply_count
                FROM forum_posts p JOIN users u ON u.id=p.author_id
                ORDER BY p.updated_at DESC, p.id DESC LIMIT 100""")
    return {"posts": [_present(row) for row in rows]}


@router.post("/posts", status_code=status.HTTP_201_CREATED)
def create_post(body: PostIn, user=Depends(current_user)):
    title, content = body.title.strip(), body.body.strip()
    if not title or not content:
        raise HTTPException(422, "A discussion title and message are required")
    created = now_s()
    post_id = ex("""INSERT INTO forum_posts(author_id, title, body, created_at, updated_at)
                    VALUES (?,?,?,?,?)""", (user["id"], title, content, created, created))
    row = q1("""SELECT p.id, p.title, p.body, p.created_at, p.updated_at, u.name AS author_name,
                       u.role AS author_role, 0 AS reply_count
                FROM forum_posts p JOIN users u ON u.id=p.author_id WHERE p.id=?""", (post_id,))
    return {"post": _present(row)}


@router.get("/posts/{post_id}")
def get_post(post_id: int, user=Depends(current_user)):
    post = q1("""SELECT p.id, p.title, p.body, p.created_at, p.updated_at, u.name AS author_name,
                        u.role AS author_role,
                        (SELECT COUNT(*) FROM forum_replies r WHERE r.post_id=p.id) AS reply_count
                 FROM forum_posts p JOIN users u ON u.id=p.author_id WHERE p.id=?""", (post_id,))
    if not post:
        raise HTTPException(404, "Discussion not found")
    replies = q("""SELECT r.id, r.body, r.created_at, u.name AS author_name, u.role AS author_role
                   FROM forum_replies r JOIN users u ON u.id=r.author_id
                   WHERE r.post_id=? ORDER BY r.id""", (post_id,))
    return {"post": _present(post), "replies": [_reply_present(row) for row in replies]}


@router.post("/posts/{post_id}/replies", status_code=status.HTTP_201_CREATED)
def create_reply(post_id: int, body: ReplyIn, user=Depends(current_user)):
    content = body.body.strip()
    if not content:
        raise HTTPException(422, "A reply message is required")
    created = now_s()
    with tx():
        if not q1("SELECT id FROM forum_posts WHERE id=?", (post_id,)):
            raise HTTPException(404, "Discussion not found")
        reply_id = ex("""INSERT INTO forum_replies(post_id, author_id, body, created_at)
                         VALUES (?,?,?,?)""", (post_id, user["id"], content, created))
        ex("UPDATE forum_posts SET updated_at=? WHERE id=?", (created, post_id))
    row = q1("""SELECT r.id, r.body, r.created_at, u.name AS author_name, u.role AS author_role
                FROM forum_replies r JOIN users u ON u.id=r.author_id WHERE r.id=?""", (reply_id,))
    return {"reply": _reply_present(row)}
