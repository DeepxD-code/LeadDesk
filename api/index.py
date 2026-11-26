import os, sys

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("DATA_DIR", "/tmp/leaddesk")
os.environ.setdefault("DISABLE_SCHEDULER", "1")

from app.main import app  # noqa: E402

__all__ = ["app"]
