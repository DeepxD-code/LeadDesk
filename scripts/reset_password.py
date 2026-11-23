"""Set a password from the command line.

    python scripts/reset_password.py <username> <new-password>

Useful on a fresh deployment, where every account still has the demo password and
nobody has signed in yet to change it. Reads the same DATA_DIR as the app, so run it
where the database lives (inside the container, or with DATA_DIR set).

    docker compose exec app python scripts/reset_password.py admin 'a-long-new-password'
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import check_password_strength, hash_password  # noqa: E402
from app.db import ex, init_db, q1, tx  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Set a LeadDesk password.")
    ap.add_argument("username")
    ap.add_argument("password")
    args = ap.parse_args()

    init_db()
    user = q1("SELECT id, username, role FROM users WHERE username=?", (args.username.strip().lower(),))
    if not user:
        print(f"No such user: {args.username}", file=sys.stderr)
        return 1
    problem = check_password_strength(args.password)
    if problem:
        print(f"Refused: {problem}", file=sys.stderr)
        return 2
    with tx():
        ex("UPDATE users SET password_hash=? WHERE id=?", (hash_password(args.password), user["id"]))
        ex("DELETE FROM sessions WHERE user_id=?", (user["id"],))
    print(f"Password set for {user['username']} ({user['role']}). Existing sessions were signed out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
