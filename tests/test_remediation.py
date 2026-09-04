import time
from unittest.mock import MagicMock, patch

from watchtower.checks import CheckResult
from watchtower.remediation import ClearTempFiles, KillRunawayProcess, build_remediations


def _breach(name="disk"):
    return CheckResult.make(name, 95.0, 90.0)


def test_clear_temp_files_dry_run_deletes_nothing(tmp_path):
    old_file = tmp_path / "old.log"
    old_file.write_text("x")
    old_time = time.time() - (48 * 3600)
    import os
    os.utime(old_file, (old_time, old_time))

    action = ClearTempFiles(path=str(tmp_path), max_age_hours=24, dry_run=True)
    result = action.apply(_breach("disk"))

    assert result.dry_run is True
    assert result.applied is False
    assert old_file.exists(), "dry_run must never delete files"
    assert "would delete 1" in result.detail


def test_clear_temp_files_real_run_deletes_old_files(tmp_path):
    old_file = tmp_path / "old.log"
    old_file.write_text("x")
    old_time = time.time() - (48 * 3600)
    import os
    os.utime(old_file, (old_time, old_time))

    new_file = tmp_path / "new.log"
    new_file.write_text("y")

    action = ClearTempFiles(path=str(tmp_path), max_age_hours=24, dry_run=False)
    result = action.apply(_breach("disk"))

    assert result.applied is True
    assert not old_file.exists()
    assert new_file.exists(), "recent files must not be touched"


def test_clear_temp_files_only_applies_to_disk():
    action = ClearTempFiles(dry_run=True)
    assert action.applies_to(_breach("disk")) is True
    assert action.applies_to(_breach("cpu")) is False


def test_kill_runaway_process_dry_run_never_terminates():
    fake_proc = MagicMock()
    fake_proc.info = {"pid": 1234, "name": "hog", "cpu_percent": 99.0}

    with patch("watchtower.remediation.psutil.process_iter", return_value=[fake_proc]):
        action = KillRunawayProcess(cpu_threshold_percent=90.0, dry_run=True)
        result = action.apply(_breach("cpu"))

    assert result.dry_run is True
    assert result.applied is False
    fake_proc.terminate.assert_not_called()
    assert "would kill" in result.detail


def test_kill_runaway_process_real_run_terminates_worst_offender():
    low = MagicMock()
    low.info = {"pid": 1, "name": "low", "cpu_percent": 91.0}
    high = MagicMock()
    high.info = {"pid": 2, "name": "high", "cpu_percent": 99.0}

    with patch("watchtower.remediation.psutil.process_iter", return_value=[low, high]):
        action = KillRunawayProcess(cpu_threshold_percent=90.0, dry_run=False)
        result = action.apply(_breach("cpu"))

    high.terminate.assert_called_once()
    low.terminate.assert_not_called()
    assert result.applied is True


def test_build_remediations_respects_enabled_flags():
    cfg = {
        "clear_temp_files": {"enabled": True, "path": "/tmp"},
        "kill_runaway_process": {"enabled": False},
    }
    remediations = build_remediations(cfg, dry_run=True)
    assert len(remediations) == 1
    assert remediations[0].name == "clear_temp_files"
