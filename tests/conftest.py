"""Test setup: run the app against a throw-away data directory, seeded once.

One TestClient per role, so each has its own cookie jar and one login cannot
overwrite another's session.
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_TMP = tempfile.mkdtemp(prefix="leaddesk-test-")
os.environ["DATA_DIR"] = _TMP
os.environ["VAULT_MASTER_KEY_FILE"] = os.path.join(_TMP, "vault_master.key")
os.environ["SEED_DEMO"] = "1"
os.environ["DEMO_MODE"] = "1"
os.environ["SMTP_DISABLED"] = "1"      # never try to reach a mail server from tests

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSWORD = "demo1234"


@pytest.fixture(scope="session")
def seeded():
    """Starts the app once: schema, vault key, demo seed, indexes."""
    with TestClient(app):
        yield


def _client(username):
    c = TestClient(app)          # no lifespan: `seeded` already ran it
    r = c.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="session")
def anon(seeded):
    return TestClient(app)


@pytest.fixture(scope="session")
def lead(seeded):
    return _client("lead")


@pytest.fixture(scope="session")
def member(seeded):
    return _client("m01")


@pytest.fixture(scope="session")
def admin(seeded):
    return _client("admin")


@pytest.fixture(scope="session")
def hr(seeded):
    return _client("hr1")


@pytest.fixture(scope="session")
def interviewer(seeded):
    return _client("int1")


@pytest.fixture(scope="session")
def interviewer2(seeded):
    return _client("int2")


@pytest.fixture(scope="session")
def tester(seeded):
    return _client("tester")


@pytest.fixture(scope="session")
def developer(seeded):
    return _client("dev")
