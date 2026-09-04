"""Configuration loading and validation for Watchtower.

Config lives in a YAML file. We fail loudly on bad config rather than
silently falling back to defaults for anything safety-related (thresholds,
dry_run), because a monitoring tool that silently misconfigures itself
is worse than one that refuses to start.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when the config file is missing, malformed, or invalid."""


DEFAULT_CONFIG: dict[str, Any] = {
    "interval_seconds": 60,
    "dry_run": True,  # safety default: remediations only log, never act
    "thresholds": {
        "cpu_percent": 90.0,
        "memory_percent": 90.0,
        "disk_percent": 90.0,
        "max_processes": 500,
    },
    "remediations": {
        "clear_temp_files": {"enabled": False, "path": "/tmp", "max_age_hours": 24},
        "kill_runaway_process": {"enabled": False, "cpu_threshold_percent": 95.0},
    },
    "notifiers": {
        "console": {"enabled": True},
        "slack": {"enabled": False, "webhook_url": ""},
    },
    "storage": {"db_path": "watchtower.db"},
    "logging": {"level": "INFO", "log_path": "watchtower.log"},
}


@dataclass
class ThresholdConfig:
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    max_processes: int


@dataclass
class AppConfig:
    interval_seconds: int
    dry_run: bool
    thresholds: ThresholdConfig
    remediations: dict[str, Any]
    notifiers: dict[str, Any]
    storage: dict[str, Any]
    logging: dict[str, Any]
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _validate(cfg: dict[str, Any]) -> None:
    errors = []

    interval = cfg.get("interval_seconds")
    if not isinstance(interval, (int, float)) or interval <= 0:
        errors.append("interval_seconds must be a positive number")

    if not isinstance(cfg.get("dry_run"), bool):
        errors.append("dry_run must be true or false")

    thresholds = cfg.get("thresholds", {})
    for key in ("cpu_percent", "memory_percent", "disk_percent"):
        val = thresholds.get(key)
        if not isinstance(val, (int, float)) or not (0 < val <= 100):
            errors.append(f"thresholds.{key} must be a number between 0 and 100")

    max_proc = thresholds.get("max_processes")
    if not isinstance(max_proc, int) or max_proc <= 0:
        errors.append("thresholds.max_processes must be a positive integer")

    slack_cfg = cfg.get("notifiers", {}).get("slack", {})
    if slack_cfg.get("enabled") and not slack_cfg.get("webhook_url"):
        errors.append("notifiers.slack.enabled is true but webhook_url is empty")

    if errors:
        raise ConfigError("Invalid config:\n  - " + "\n  - ".join(errors))


def load_config(path: str | Path | None) -> AppConfig:
    """Load config from `path`, merged over defaults. `path=None` uses defaults only."""
    merged = copy.deepcopy(DEFAULT_CONFIG)

    if path is not None:
        path = Path(path)
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            with path.open("r") as f:
                user_cfg = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Could not parse YAML in {path}: {e}") from e
        if not isinstance(user_cfg, dict):
            raise ConfigError(f"Top-level config in {path} must be a mapping")
        merged = _deep_merge(merged, user_cfg)

    _validate(merged)

    return AppConfig(
        interval_seconds=int(merged["interval_seconds"]),
        dry_run=bool(merged["dry_run"]),
        thresholds=ThresholdConfig(**merged["thresholds"]),
        remediations=merged["remediations"],
        notifiers=merged["notifiers"],
        storage=merged["storage"],
        logging=merged["logging"],
        raw=merged,
    )
