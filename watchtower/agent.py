"""The Watchtower agent: runs on each monitored host, runs checks on a
background thread, and exposes them at /metrics in Prometheus format for
a central Prometheus server to scrape.

Deliberately thin. No dashboard HTML, no notifiers, no remediation logic
here - those are central-server concerns in the fleet architecture
(Prometheus stores history, Grafana visualizes, Alertmanager alerts and
dedups). The agent's only job is "run checks, answer /metrics when asked."
Keeping it minimal is what makes it reasonable to run one per host across
a fleet, rather than a heavyweight process per machine.

This intentionally reuses the same Check classes as the single-host CLI
(`watchtower check` / `watchtower run`) - one source of truth for what a
check is, two different ways of consuming its output (local CLI/SQLite vs.
Prometheus scrape).
"""
from __future__ import annotations

import logging
import socket
import threading

from flask import Flask, Response

from watchtower.checks import build_default_checks
from watchtower.config import AppConfig
from watchtower.metrics import CONTENT_TYPE_LATEST, MetricsRegistry

logger = logging.getLogger("watchtower.agent")


class Agent:
    """Runs checks on a background thread at config.interval_seconds,
    updating a MetricsRegistry that the Flask app serves on scrape.
    """

    def __init__(self, config: AppConfig, hostname: str | None = None):
        self.config = config
        self.hostname = hostname or socket.gethostname()
        self.checks = build_default_checks(config.thresholds)
        self.metrics = MetricsRegistry()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            results = []
            for check in self.checks:
                try:
                    results.append(check.run())
                except Exception:
                    logger.exception("Check %s failed on agent %s", check.name, self.hostname)
            self.metrics.update(results)
            self._stop_event.wait(self.config.interval_seconds)

    def start_background(self) -> None:
        """Starts the check loop on a daemon thread so it runs alongside
        the Flask web server in the same process.
        """
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="watchtower-agent-loop")
        self._thread.start()
        logger.info("Agent started for host=%s interval=%ss", self.hostname, self.config.interval_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def run_once_sync(self) -> None:
        """Runs one check cycle synchronously and updates metrics. Used by
        tests and by the /metrics handler as a fallback if the background
        loop hasn't populated anything yet.
        """
        results = [c.run() for c in self.checks]
        self.metrics.update(results)


def create_agent_app(config: AppConfig, hostname: str | None = None) -> Flask:
    app = Flask(__name__)
    agent = Agent(config, hostname=hostname)

    # Populate metrics once synchronously so the very first scrape (before
    # the background loop's first tick) doesn't return empty gauges.
    agent.run_once_sync()
    agent.start_background()

    app.config["watchtower_agent"] = agent

    @app.route("/metrics")
    def metrics_endpoint():
        return Response(agent.metrics.render(), mimetype=CONTENT_TYPE_LATEST)

    @app.route("/healthz")
    def healthz():
        return {"status": "ok", "hostname": agent.hostname}

    return app
