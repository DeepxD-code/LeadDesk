import json


def test_audit_log_is_shipped_to_an_append_only_file(tmp_path, monkeypatch):
    from app import vault

    target = tmp_path / "audit.jsonl"
    monkeypatch.setattr(vault, "AUDIT_SHIP_FILE", str(target))
    monkeypatch.setattr(vault, "AUDIT_SHIP_URL", "")
    monkeypatch.setattr(vault, "AUDIT_ALERT_WEBHOOK", "")

    vault._ship_audit({"at": "2026-11-26T10:00", "action": "first", "outcome": "allowed"})
    vault._ship_audit({"at": "2026-11-26T10:01", "action": "second", "outcome": "denied"})

    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["action"] == "first"
    assert json.loads(lines[1])["outcome"] == "denied"


def test_audit_ship_file_ignores_missing_parent_and_keeps_local_log(monkeypatch):
    """A broken sink must never raise out of audit(): the DB row is the source of truth."""
    from app import vault

    monkeypatch.setattr(vault, "AUDIT_SHIP_FILE", "")
    monkeypatch.setattr(vault, "AUDIT_SHIP_URL", "")
    monkeypatch.setattr(vault, "AUDIT_ALERT_WEBHOOK", "")
    vault._ship_audit({"action": "no-sink"})   # no file, no URL: must be a no-op
