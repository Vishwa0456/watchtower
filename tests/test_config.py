import pytest

from watchtower.config import ConfigError, load_config


def test_default_config_loads():
    cfg = load_config(None)
    assert cfg.dry_run is True
    assert cfg.thresholds.cpu_percent == 90.0


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "does_not_exist.yaml")


def test_invalid_threshold_raises(tmp_path):
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text("thresholds:\n  cpu_percent: 150\n")
    with pytest.raises(ConfigError, match="cpu_percent"):
        load_config(bad_config)


def test_slack_enabled_without_webhook_raises(tmp_path):
    bad_config = tmp_path / "bad_slack.yaml"
    bad_config.write_text("notifiers:\n  slack:\n    enabled: true\n    webhook_url: ''\n")
    with pytest.raises(ConfigError, match="webhook_url"):
        load_config(bad_config)


def test_user_config_overrides_defaults(tmp_path):
    cfg_file = tmp_path / "custom.yaml"
    cfg_file.write_text("interval_seconds: 30\nthresholds:\n  cpu_percent: 75\n")
    cfg = load_config(cfg_file)
    assert cfg.interval_seconds == 30
    assert cfg.thresholds.cpu_percent == 75.0
    # unspecified thresholds should still come from defaults
    assert cfg.thresholds.memory_percent == 90.0


def test_malformed_yaml_raises(tmp_path):
    bad_config = tmp_path / "malformed.yaml"
    bad_config.write_text("thresholds: [this is not: valid: yaml")
    with pytest.raises(ConfigError):
        load_config(bad_config)
