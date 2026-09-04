"""Notification channels. Each notifier implements `send(message)`. Add a
new channel (email, PagerDuty, etc.) by subclassing Notifier - the engine
doesn't need to know the details.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import requests

logger = logging.getLogger("watchtower")


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str) -> None:
        ...


class ConsoleNotifier(Notifier):
    def send(self, message: str) -> None:
        print(f"[ALERT] {message}")


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str, timeout_seconds: float = 5.0):
        if not webhook_url:
            raise ValueError("SlackNotifier requires a non-empty webhook_url")
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds

    def send(self, message: str) -> None:
        try:
            resp = requests.post(
                self.webhook_url,
                json={"text": message},
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            # A failed alert should never crash the monitoring loop - log
            # it and move on. Silent alert failures are worse than a noisy
            # log line, but a dead monitor is worse than either.
            logger.error("Slack notification failed: %s", e)


def build_notifiers(cfg: dict) -> list[Notifier]:
    notifiers: list[Notifier] = []

    if cfg.get("console", {}).get("enabled"):
        notifiers.append(ConsoleNotifier())

    slack_cfg = cfg.get("slack", {})
    if slack_cfg.get("enabled"):
        notifiers.append(SlackNotifier(webhook_url=slack_cfg.get("webhook_url", "")))

    return notifiers
