from unittest.mock import patch

from watchtower.config import load_config
from watchtower.web import create_app


def _client(tmp_path):
    config = load_config(None)
    config.storage["db_path"] = str(tmp_path / "test.db")
    app = create_app(config)
    app.config.update(TESTING=True)
    return app.test_client()


@patch("watchtower.checks.psutil.cpu_percent", return_value=5.0)
@patch("watchtower.checks.psutil.virtual_memory")
@patch("watchtower.checks.psutil.disk_usage")
@patch("watchtower.checks.psutil.pids", return_value=list(range(10)))
def test_dashboard_page_loads(mock_pids, mock_disk, mock_mem, mock_cpu, tmp_path):
    mock_mem.return_value.percent = 10.0
    mock_disk.return_value.percent = 20.0
    client = _client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Watchtower" in resp.data


@patch("watchtower.checks.psutil.cpu_percent", return_value=5.0)
@patch("watchtower.checks.psutil.virtual_memory")
@patch("watchtower.checks.psutil.disk_usage")
@patch("watchtower.checks.psutil.pids", return_value=list(range(10)))
def test_api_status_returns_json(mock_pids, mock_disk, mock_mem, mock_cpu, tmp_path):
    mock_mem.return_value.percent = 10.0
    mock_disk.return_value.percent = 20.0
    client = _client(tmp_path)
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "checks" in data
    assert len(data["checks"]) == 4


def test_healthz(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


@patch("watchtower.checks.psutil.cpu_percent", return_value=5.0)
@patch("watchtower.checks.psutil.virtual_memory")
@patch("watchtower.checks.psutil.disk_usage")
@patch("watchtower.checks.psutil.pids", return_value=list(range(10)))
def test_dashboard_load_records_to_storage(mock_pids, mock_disk, mock_mem, mock_cpu, tmp_path):
    """The dashboard's whole trend-chart feature depends on each page hit
    writing a data point - this is the behavior that makes that possible.
    """
    mock_mem.return_value.percent = 10.0
    mock_disk.return_value.percent = 20.0
    client = _client(tmp_path)

    client.get("/")
    client.get("/")
    client.get("/")

    resp = client.get("/api/history?name=cpu&limit=10")
    data = resp.get_json()
    assert len(data["values"]) == 3
    assert all(v == 5.0 for v in data["values"])


@patch("watchtower.checks.psutil.cpu_percent", return_value=5.0)
@patch("watchtower.checks.psutil.virtual_memory")
@patch("watchtower.checks.psutil.disk_usage")
@patch("watchtower.checks.psutil.pids", return_value=list(range(10)))
def test_api_history_respects_limit(mock_pids, mock_disk, mock_mem, mock_cpu, tmp_path):
    mock_mem.return_value.percent = 10.0
    mock_disk.return_value.percent = 20.0
    client = _client(tmp_path)

    for _ in range(5):
        client.get("/api/status")

    resp = client.get("/api/history?name=cpu&limit=2")
    data = resp.get_json()
    assert len(data["values"]) == 2


def test_api_history_unknown_check_returns_empty(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/history?name=nonexistent")
    assert resp.status_code == 200
    assert resp.get_json()["values"] == []
