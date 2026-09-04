"""Health checks. Each check inspects one system dimension and returns a
CheckResult. New checks plug in by subclassing Check - nothing else in the
codebase needs to change (open/closed principle).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import psutil


@dataclass
class CheckResult:
    name: str
    value: float
    threshold: float
    breached: bool
    message: str
    timestamp: str

    @classmethod
    def make(cls, name: str, value: float, threshold: float, unit: str = "%") -> CheckResult:
        breached = value > threshold
        status = "BREACH" if breached else "ok"
        return cls(
            name=name,
            value=value,
            threshold=threshold,
            breached=breached,
            message=f"{name}: {value:.1f}{unit} (threshold {threshold:.1f}{unit}) [{status}]",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


class Check(ABC):
    """Base class for all health checks."""

    name: str

    @abstractmethod
    def run(self) -> CheckResult:
        ...


class CPUCheck(Check):
    name = "cpu"

    def __init__(self, threshold_percent: float, sample_seconds: float = 0.5):
        self.threshold = threshold_percent
        self.sample_seconds = sample_seconds

    def run(self) -> CheckResult:
        value = psutil.cpu_percent(interval=self.sample_seconds)
        return CheckResult.make(self.name, value, self.threshold)


class MemoryCheck(Check):
    name = "memory"

    def __init__(self, threshold_percent: float):
        self.threshold = threshold_percent

    def run(self) -> CheckResult:
        value = psutil.virtual_memory().percent
        return CheckResult.make(self.name, value, self.threshold)


class DiskCheck(Check):
    name = "disk"

    def __init__(self, threshold_percent: float, mount_point: str = "/"):
        self.threshold = threshold_percent
        self.mount_point = mount_point

    def run(self) -> CheckResult:
        value = psutil.disk_usage(self.mount_point).percent
        return CheckResult.make(self.name, value, self.threshold)


class ProcessCountCheck(Check):
    name = "process_count"

    def __init__(self, max_processes: int):
        self.threshold = max_processes

    def run(self) -> CheckResult:
        value = len(psutil.pids())
        return CheckResult.make(self.name, value, self.threshold, unit=" procs")


def build_default_checks(thresholds) -> list[Check]:
    """Factory: builds the standard check set from a ThresholdConfig."""
    return [
        CPUCheck(thresholds.cpu_percent),
        MemoryCheck(thresholds.memory_percent),
        DiskCheck(thresholds.disk_percent),
        ProcessCountCheck(thresholds.max_processes),
    ]
