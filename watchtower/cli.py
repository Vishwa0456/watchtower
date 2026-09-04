"""Command-line interface for Watchtower.

Subcommands:
  watchtower run              - run continuously on the configured interval
  watchtower check            - run all checks once and print results, then exit
  watchtower history          - show recent breached checks from storage
  watchtower init-config      - write a starter config.yaml
  watchtower serve            - run a read-only web dashboard (view from any browser)
  watchtower agent            - run the Prometheus-metrics agent (for fleet monitoring)
"""
from __future__ import annotations

import argparse
import sys

from watchtower.config import ConfigError, load_config
from watchtower.engine import Engine
from watchtower.logging_setup import setup_logging
from watchtower.storage import Storage

STARTER_CONFIG = """\
# Watchtower configuration
interval_seconds: 60

# Safety switch. When true (default), remediations compute and log/notify
# what they WOULD do but take no destructive action. Flip to false only
# once you've reviewed dry-run output and trust the thresholds below.
dry_run: true

thresholds:
  cpu_percent: 90
  memory_percent: 90
  disk_percent: 90
  max_processes: 500

remediations:
  clear_temp_files:
    enabled: false
    path: /tmp
    max_age_hours: 24
  kill_runaway_process:
    enabled: false
    cpu_threshold_percent: 95

notifiers:
  console:
    enabled: true
  slack:
    enabled: false
    webhook_url: ""

storage:
  db_path: watchtower.db

logging:
  level: INFO
  log_path: watchtower.log
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="watchtower", description=__doc__)
    parser.add_argument(
        "-c", "--config", default=None,
        help="Path to config YAML (defaults to built-in defaults)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Run continuously on the configured interval")
    sub.add_parser("check", help="Run all checks once and exit")

    hist = sub.add_parser("history", help="Show recent breached checks")
    hist.add_argument("-n", "--limit", type=int, default=20, help="Number of incidents to show")

    init_cfg = sub.add_parser("init-config", help="Write a starter config.yaml")
    init_cfg.add_argument("-o", "--output", default="config.yaml", help="Output path")

    serve = sub.add_parser("serve", help="Run a read-only web dashboard")
    serve.add_argument("--host", default="0.0.0.0", help="Bind host (default 0.0.0.0)")
    serve.add_argument("--port", type=int, default=8000, help="Bind port (default 8000)")

    agent = sub.add_parser("agent", help="Run the Prometheus-metrics agent")
    agent.add_argument("--host", default="0.0.0.0", help="Bind host (default 0.0.0.0)")
    agent.add_argument("--port", type=int, default=9100, help="Bind port (default 9100)")
    agent.add_argument("--hostname", default=None, help="Override reported hostname label")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-config":
        with open(args.output, "w") as f:
            f.write(STARTER_CONFIG)
        print(f"Wrote starter config to {args.output}")
        return 0

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    setup_logging(config.logging.get("level", "INFO"), config.logging.get("log_path", "watchtower.log"))

    if args.command == "check":
        engine = Engine(config)
        results = engine.run_once()
        breached = [r for r in results if r.breached]
        for r in results:
            print(r.message)
        return 1 if breached else 0

    if args.command == "run":
        engine = Engine(config)
        engine.run_forever()
        return 0

    if args.command == "serve":
        from watchtower.web import create_app
        app = create_app(config)
        app.run(host=args.host, port=args.port)
        return 0

    if args.command == "agent":
        from watchtower.agent import create_agent_app
        app = create_agent_app(config, hostname=args.hostname)
        app.run(host=args.host, port=args.port)
        return 0

    if args.command == "history":
        storage = Storage(config.storage["db_path"])
        rows = storage.recent_incidents(limit=args.limit)
        storage.close()
        if not rows:
            print("No recorded incidents.")
            return 0
        for row in rows:
            print(f"{row['timestamp']}  {row['message']}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
