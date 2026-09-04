"""Prometheus metrics for Watchtower agents.

Uses the official `prometheus_client` library rather than hand-rolling the
exposition text format. Each check result updates a Gauge; Prometheus
scrapes `/metrics` on its own schedule (pull model), independent of
Watchtower's own check interval.

Metric naming follows Prometheus convention: `<namespace>_<unit>` with a
`_percent` or `_total` suffix, e.g. `watchtower_cpu_percent`.
"""
from __future__ import annotations

import time

from prometheus_client import CollectorRegistry, Gauge, generate_latest

from watchtower.checks import CheckResult

CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


class MetricsRegistry:
    """Wraps a Prometheus CollectorRegistry with the gauges Watchtower needs.

    A fresh CollectorRegistry (not the global default) is used so multiple
    agents can exist in the same test process without metric name
    collisions - the default registry is a process-wide singleton and
    would break test isolation.
    """

    def __init__(self):
        self.registry = CollectorRegistry()

        self.cpu_percent = Gauge(
            "watchtower_cpu_percent", "CPU utilization percent", registry=self.registry
        )
        self.memory_percent = Gauge(
            "watchtower_memory_percent", "Memory utilization percent", registry=self.registry
        )
        self.disk_percent = Gauge(
            "watchtower_disk_percent", "Disk utilization percent", registry=self.registry
        )
        self.process_count = Gauge(
            "watchtower_process_count", "Number of running processes", registry=self.registry
        )
        self.check_breached = Gauge(
            "watchtower_check_breached",
            "Whether a check is currently breached (1) or not (0)",
            ["check_name"],
            registry=self.registry,
        )
        self.last_check_timestamp = Gauge(
            "watchtower_last_check_timestamp_seconds",
            "Unix timestamp of the most recent check cycle",
            registry=self.registry,
        )

    def update(self, results: list[CheckResult]) -> None:
        gauge_map = {
            "cpu": self.cpu_percent,
            "memory": self.memory_percent,
            "disk": self.disk_percent,
            "process_count": self.process_count,
        }
        for result in results:
            gauge = gauge_map.get(result.name)
            if gauge is not None:
                gauge.set(result.value)
            self.check_breached.labels(check_name=result.name).set(1 if result.breached else 0)

        self.last_check_timestamp.set(time.time())

    def render(self) -> bytes:
        return generate_latest(self.registry)
