from unittest.mock import MagicMock, patch

from watchtower.checks import CPUCheck, DiskCheck, MemoryCheck, ProcessCountCheck


@patch("watchtower.checks.psutil.cpu_percent", return_value=95.0)
def test_cpu_check_breach(mock_cpu):
    result = CPUCheck(threshold_percent=90.0, sample_seconds=0).run()
    assert result.breached is True
    assert result.value == 95.0
    assert result.name == "cpu"


@patch("watchtower.checks.psutil.cpu_percent", return_value=10.0)
def test_cpu_check_no_breach(mock_cpu):
    result = CPUCheck(threshold_percent=90.0, sample_seconds=0).run()
    assert result.breached is False


@patch("watchtower.checks.psutil.virtual_memory")
def test_memory_check(mock_mem):
    mock_mem.return_value = MagicMock(percent=50.0)
    result = MemoryCheck(threshold_percent=90.0).run()
    assert result.breached is False
    assert result.value == 50.0


@patch("watchtower.checks.psutil.disk_usage")
def test_disk_check_breach(mock_disk):
    mock_disk.return_value = MagicMock(percent=99.0)
    result = DiskCheck(threshold_percent=90.0).run()
    assert result.breached is True


@patch("watchtower.checks.psutil.pids", return_value=list(range(600)))
def test_process_count_breach(mock_pids):
    result = ProcessCountCheck(max_processes=500).run()
    assert result.breached is True
    assert result.value == 600


def test_check_result_message_format():
    from watchtower.checks import CheckResult
    r = CheckResult.make("cpu", 95.5, 90.0)
    assert "cpu" in r.message
    assert "BREACH" in r.message
