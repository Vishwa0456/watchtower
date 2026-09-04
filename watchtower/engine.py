"""Orchestrates one monitoring cycle: run checks -> store results ->
apply remediations for breaches -> notify.
"""
from __future__ import annotations

import logging
import time

from watchtower.checks import Check, CheckResult, build_default_checks
from watchtower.config import AppConfig
from watchtower.notifiers import Notifier, build_notifiers
from watchtower.remediation import Remediation, build_remediations
from watchtower.storage import Storage

logger = logging.getLogger("watchtower")


class Engine:
    def __init__(
        self,
        config: AppConfig,
        checks: list[Check] | None = None,
        remediations: list[Remediation] | None = None,
        notifiers: list[Notifier] | None = None,
        storage: Storage | None = None,
    ):
        self.config = config
        self.checks = checks if checks is not None else build_default_checks(config.thresholds)
        self.remediations = (
            remediations if remediations is not None
            else build_remediations(config.remediations, config.dry_run)
        )
        self.notifiers = notifiers if notifiers is not None else build_notifiers(config.notifiers)
        self.storage = storage if storage is not None else Storage(config.storage["db_path"])

    def run_once(self) -> list[CheckResult]:
        """Runs all checks once, storing and reacting to results. Returns
        the list of results so callers (CLI, tests) can inspect them.
        """
        results = []
        for check in self.checks:
            try:
                result = check.run()
            except Exception:
                logger.exception("Check %s raised an exception - skipping", check.name)
                continue

            results.append(result)
            self.storage.record_check(result)
            logger.info(result.message)

            if result.breached:
                self._handle_breach(result)

        return results

    def _handle_breach(self, result: CheckResult) -> None:
        for notifier in self.notifiers:
            try:
                notifier.send(result.message)
            except Exception:
                logger.exception("Notifier %s failed", type(notifier).__name__)

        for remediation in self.remediations:
            if not remediation.applies_to(result):
                continue
            try:
                rem_result = remediation.apply(result)
            except Exception:
                logger.exception("Remediation %s raised an exception", remediation.name)
                continue

            self.storage.record_remediation(result.name, rem_result, result.timestamp)
            logger.info(
                "remediation=%s dry_run=%s applied=%s detail=%s",
                rem_result.name, rem_result.dry_run, rem_result.applied, rem_result.detail,
            )

            if rem_result.dry_run:
                for notifier in self.notifiers:
                    try:
                        notifier.send(f"[DRY-RUN] {rem_result.name}: {rem_result.detail}")
                    except Exception:
                        logger.exception("Notifier %s failed", type(notifier).__name__)

    def run_forever(self) -> None:
        """Runs checks on a loop at config.interval_seconds until interrupted."""
        logger.info(
            "Watchtower starting: interval=%ss dry_run=%s",
            self.config.interval_seconds, self.config.dry_run,
        )
        try:
            while True:
                self.run_once()
                time.sleep(self.config.interval_seconds)
        except KeyboardInterrupt:
            logger.info("Watchtower stopped by user")
        finally:
            self.storage.close()
