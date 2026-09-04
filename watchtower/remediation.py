"""Remediation actions taken in response to a breached check.

Safety model: every remediation takes `dry_run` as a constructor argument.
When dry_run is True (the default in config.py), `apply()` computes and
returns what it WOULD do, but performs no destructive action. This is
deliberate - an automated tool that can kill processes or delete files
needs an explicit, auditable opt-in before it's allowed to act for real.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import psutil

from watchtower.checks import CheckResult


@dataclass
class RemediationResult:
    name: str
    dry_run: bool
    applied: bool
    detail: str


class Remediation(ABC):
    name: str

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    @abstractmethod
    def applies_to(self, result: CheckResult) -> bool:
        """Whether this remediation is relevant to a given breached check."""

    @abstractmethod
    def apply(self, result: CheckResult) -> RemediationResult:
        ...


class ClearTempFiles(Remediation):
    """Deletes files older than `max_age_hours` under `path`. Only relevant
    to disk-space breaches.
    """

    name = "clear_temp_files"

    def __init__(self, path: str = "/tmp", max_age_hours: float = 24, dry_run: bool = True):
        super().__init__(dry_run)
        self.path = Path(path)
        self.max_age_seconds = max_age_hours * 3600

    def applies_to(self, result: CheckResult) -> bool:
        return result.name == "disk" and result.breached

    def apply(self, result: CheckResult) -> RemediationResult:
        if not self.path.exists():
            return RemediationResult(self.name, self.dry_run, False, f"{self.path} does not exist")

        now = time.time()
        candidates = []
        for entry in self.path.glob("*"):
            try:
                if entry.is_file() and (now - entry.stat().st_mtime) > self.max_age_seconds:
                    candidates.append(entry)
            except OSError:
                continue  # file vanished or permission denied mid-scan; skip it

        if self.dry_run:
            return RemediationResult(
                self.name, True, False,
                f"would delete {len(candidates)} file(s) older than "
                f"{self.max_age_seconds / 3600:.0f}h under {self.path}",
            )

        deleted = 0
        for entry in candidates:
            try:
                entry.unlink()
                deleted += 1
            except OSError:
                continue
        return RemediationResult(self.name, False, True, f"deleted {deleted} file(s) under {self.path}")


class KillRunawayProcess(Remediation):
    """Kills the single highest-CPU process above `cpu_threshold_percent`,
    excluding this tool's own PID. Only relevant to CPU breaches.
    """

    name = "kill_runaway_process"

    def __init__(self, cpu_threshold_percent: float = 95.0, dry_run: bool = True):
        super().__init__(dry_run)
        self.cpu_threshold_percent = cpu_threshold_percent

    def applies_to(self, result: CheckResult) -> bool:
        return result.name == "cpu" and result.breached

    def apply(self, result: CheckResult) -> RemediationResult:
        own_pid = os.getpid()
        worst = None
        for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
            if proc.info["pid"] == own_pid:
                continue
            cpu = proc.info["cpu_percent"] or 0.0
            if cpu >= self.cpu_threshold_percent and (worst is None or cpu > worst.info["cpu_percent"]):
                worst = proc

        if worst is None:
            return RemediationResult(
                self.name, self.dry_run, False,
                f"no process found above {self.cpu_threshold_percent:.0f}% CPU",
            )

        detail = f"pid={worst.info['pid']} name={worst.info['name']} cpu={worst.info['cpu_percent']:.1f}%"
        if self.dry_run:
            return RemediationResult(self.name, True, False, f"would kill {detail}")

        try:
            worst.terminate()
            return RemediationResult(self.name, False, True, f"terminated {detail}")
        except psutil.NoSuchProcess:
            return RemediationResult(self.name, False, False, f"process gone before kill: {detail}")
        except psutil.AccessDenied:
            return RemediationResult(self.name, False, False, f"access denied killing {detail}")


def build_remediations(cfg: dict, dry_run: bool) -> list[Remediation]:
    """Factory: builds enabled remediations from the `remediations` config block."""
    remediations: list[Remediation] = []

    ctf = cfg.get("clear_temp_files", {})
    if ctf.get("enabled"):
        remediations.append(ClearTempFiles(
            path=ctf.get("path", "/tmp"),
            max_age_hours=ctf.get("max_age_hours", 24),
            dry_run=dry_run,
        ))

    krp = cfg.get("kill_runaway_process", {})
    if krp.get("enabled"):
        remediations.append(KillRunawayProcess(
            cpu_threshold_percent=krp.get("cpu_threshold_percent", 95.0),
            dry_run=dry_run,
        ))

    return remediations
