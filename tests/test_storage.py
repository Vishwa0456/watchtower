from watchtower.checks import CheckResult
from watchtower.remediation import RemediationResult
from watchtower.storage import Storage


def test_record_and_read_check(tmp_path):
    db_path = tmp_path / "test.db"
    storage = Storage(db_path)

    breached = CheckResult.make("cpu", 95.0, 90.0)
    ok = CheckResult.make("memory", 10.0, 90.0)
    storage.record_check(breached)
    storage.record_check(ok)

    incidents = storage.recent_incidents(limit=10)
    assert len(incidents) == 1
    assert incidents[0]["name"] == "cpu"
    storage.close()


def test_record_remediation(tmp_path):
    db_path = tmp_path / "test.db"
    with Storage(db_path) as storage:
        rem_result = RemediationResult(
            "clear_temp_files", dry_run=True, applied=False, detail="would delete 3"
        )
        storage.record_remediation("disk", rem_result, "2026-01-01T00:00:00Z")

        with storage._connect() as conn:
            rows = conn.execute("SELECT * FROM remediation_results").fetchall()
        assert len(rows) == 1


def test_recent_incidents_respects_limit(tmp_path):
    db_path = tmp_path / "test.db"
    storage = Storage(db_path)
    for i in range(5):
        storage.record_check(CheckResult.make("cpu", 95.0 + i, 90.0))
    incidents = storage.recent_incidents(limit=2)
    assert len(incidents) == 2
    storage.close()
