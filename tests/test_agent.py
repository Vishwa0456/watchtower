from unittest.mock import patch

from watchtower.agent import Agent, create_agent_app
from watchtower.config import load_config


def _config():
    return load_config(None)


@patch("watchtower.checks.psutil.cpu_percent", return_value=5.0)
@patch("watchtower.checks.psutil.virtual_memory")
@patch("watchtower.checks.psutil.disk_usage")
@patch("watchtower.checks.psutil.pids", return_value=list(range(10)))
def test_agent_run_once_sync_populates_metrics(mock_pids, mock_disk, mock_mem, mock_cpu):
    mock_mem.return_value.percent = 10.0
    mock_disk.return_value.percent = 20.0

    agent = Agent(_config(), hostname="test-host")
    agent.run_once_sync()

    output = agent.metrics.render().decode()
    assert "watchtower_cpu_percent 5.0" in output


def test_agent_default_hostname_is_socket_hostname():
    agent = Agent(_config())
    import socket
    assert agent.hostname == socket.gethostname()


def test_agent_explicit_hostname_overrides_default():
    agent = Agent(_config(), hostname="custom-host")
    assert agent.hostname == "custom-host"


@patch("watchtower.checks.psutil.cpu_percent", return_value=5.0)
@patch("watchtower.checks.psutil.virtual_memory")
@patch("watchtower.checks.psutil.disk_usage")
@patch("watchtower.checks.psutil.pids", return_value=list(range(10)))
def test_metrics_endpoint_returns_prometheus_format(mock_pids, mock_disk, mock_mem, mock_cpu):
    mock_mem.return_value.percent = 10.0
    mock_disk.return_value.percent = 20.0

    app = create_agent_app(_config(), hostname="test-host")
    client = app.test_client()
    resp = client.get("/metrics")

    assert resp.status_code == 200
    assert b"watchtower_cpu_percent" in resp.data
    assert resp.content_type.startswith("text/plain")


@patch("watchtower.checks.psutil.cpu_percent", return_value=5.0)
@patch("watchtower.checks.psutil.virtual_memory")
@patch("watchtower.checks.psutil.disk_usage")
@patch("watchtower.checks.psutil.pids", return_value=list(range(10)))
def test_healthz_endpoint(mock_pids, mock_disk, mock_mem, mock_cpu):
    mock_mem.return_value.percent = 10.0
    mock_disk.return_value.percent = 20.0

    app = create_agent_app(_config(), hostname="test-host")
    client = app.test_client()
    resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.get_json()["hostname"] == "test-host"


def test_agent_start_stop_background_thread():
    config = _config()
    config.interval_seconds = 1  # fast loop for the test
    agent = Agent(config, hostname="test-host")
    agent.start_background()
    assert agent._thread is not None
    assert agent._thread.is_alive()
    agent.stop()
    assert not agent._thread.is_alive()
