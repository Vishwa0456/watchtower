# Watchtower

A system health monitor with configurable, **safe-by-default** auto-remediation, a CLI, and a read-only web dashboard.

Watchtower watches CPU, memory, disk, and process count on a schedule. When a threshold is breached, it logs the incident, stores it in SQLite, sends an alert (console or Slack), and — only if you've explicitly opted in — takes a remediation action.

[![CI](https://github.com/Vishwa0456/watchtower/actions/workflows/ci.yml/badge.svg)](https://github.com/Vishwa0456/watchtower/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Table of contents

- [Why this project exists](#why-this-project-exists)
- [Key design decision: dry-run by default](#key-design-decision-dry-run-by-default)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration reference](#configuration-reference)
- [Fleet architecture (Phase 1)](#fleet-architecture-phase-1-agent--prometheus-metrics)
- [Web dashboard](#web-dashboard)
- [Deploying so it's viewable from your phone](#deploying-so-its-viewable-from-your-phone)
- [Testing](#testing)
- [Docker](#docker)
- [CI/CD](#cicd)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)
- [Possible extensions](#possible-extensions)
- [License](#license)

---

## Why this project exists

Most "monitoring script" portfolio projects are a single file that prints CPU usage once. Watchtower is scoped to actually demonstrate the practices around a monitoring tool, not just the metric-reading itself:

- Config-driven behavior (YAML, validated, not hardcoded constants)
- A pluggable architecture (new checks/remediations/alert channels are one subclass, not a rewrite)
- A real safety model for anything that takes destructive action
- Persistent history (SQLite), not just stdout
- Automated tests that actually verify the safety-critical behavior (see [Testing](#testing))
- CI that lints and tests on every push
- Two ways to run it: CLI (for a server/cron context) and a read-only web dashboard (for viewing status from anywhere)

## Key design decision: dry-run by default

Watchtower can be configured to kill runaway processes and delete old temp files. An automated tool with that power is dangerous if its thresholds are wrong.

So: `dry_run: true` is the default. Every remediation still runs its full logic — it computes exactly what it *would* delete or kill — but takes no destructive action. It logs the decision and sends the same alert a real action would trigger. You only get real deletions/kills after you've watched the dry-run output and explicitly set `dry_run: false`.

This single decision is the most defensible part of the design if you're asked about it in an interview: it separates "detecting a problem" from "acting on a problem," and makes the second step an explicit, auditable opt-in.

## Architecture

```
watchtower/
├── checks.py          # Check (ABC) -> CPUCheck, MemoryCheck, DiskCheck, ProcessCountCheck
├── remediation.py      # Remediation (ABC) -> ClearTempFiles, KillRunawayProcess
├── notifiers.py         # Notifier (ABC) -> ConsoleNotifier, SlackNotifier
├── storage.py            # SQLite persistence, thread-safe (per-call connections)
├── config.py               # YAML loading, merge-with-defaults, validation
├── engine.py                 # Orchestrates: run checks -> store -> remediate -> notify
├── logging_setup.py           # Rotating file + console logging
├── web.py                      # Flask read-only dashboard + JSON API
└── cli.py                       # argparse CLI: run / check / history / init-config / serve
```

Checks, remediations, and notifiers are each a small abstract base class with one method to implement (`run()`, `apply()`, `send()`). Adding a new metric (say, network latency) or a new alert channel (say, PagerDuty) means writing one new subclass — nothing else in the codebase changes. This is the Open/Closed Principle applied to something small enough to read end-to-end in fifteen minutes, and it's the same extension pattern real monitoring systems use (Prometheus exporters, Nagios plugins) at a much larger scale.

**Data flow for one check cycle:**

```
Engine.run_once()
  -> for each Check: check.run() -> CheckResult
  -> Storage.record_check(result)
  -> if result.breached:
       -> for each Notifier: notifier.send(result.message)
       -> for each Remediation where applies_to(result):
            -> remediation.apply(result) -> RemediationResult
            -> Storage.record_remediation(...)
            -> if dry_run: notify what WOULD have happened
```

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/YOUR_USERNAME/watchtower.git
cd watchtower
pip install -r requirements-dev.txt   # runtime + test + lint deps
pip install -e .                       # installs the `watchtower` command
```

Or runtime-only, no dev tooling:

```bash
pip install -r requirements.txt
pip install -e .
```

## Usage

```bash
# Run all checks once, print results, exit 0 if clean / 1 if anything breached
watchtower check

# Generate a starter config you can edit
watchtower init-config -o config.yaml

# Run continuously against your config (Ctrl+C to stop)
watchtower -c config.yaml run

# See recent breaches from storage
watchtower history -n 10

# Run the read-only web dashboard on port 8000
watchtower -c config.yaml serve --port 8000
```

Example output of `watchtower check`:

```
cpu: 4.2% (threshold 90.0%) [ok]
memory: 61.3% (threshold 90.0%) [ok]
disk: 46.4% (threshold 90.0%) [ok]
process_count: 187.0 procs (threshold 500.0 procs) [ok]
```

Example output when a threshold is breached:

```
[ALERT] disk: 93.1% (threshold 90.0%) [BREACH]
[DRY-RUN] clear_temp_files: would delete 42 file(s) older than 24h under /tmp
```

## Configuration reference

Full example with comments: [`config/config.example.yaml`](config/config.example.yaml).

| Field | Type | Purpose |
|---|---|---|
| `interval_seconds` | int | How often `run` executes the check cycle |
| `dry_run` | bool | Safety switch — `true` means log/alert only, no destructive action |
| `thresholds.cpu_percent` | float (0-100) | CPU breach threshold |
| `thresholds.memory_percent` | float (0-100) | Memory breach threshold |
| `thresholds.disk_percent` | float (0-100) | Disk breach threshold |
| `thresholds.max_processes` | int | Process-count breach threshold |
| `remediations.clear_temp_files.enabled` | bool | Opt in to the temp-file cleanup remediation |
| `remediations.clear_temp_files.path` | str | Directory to clean |
| `remediations.clear_temp_files.max_age_hours` | float | Only delete files older than this |
| `remediations.kill_runaway_process.enabled` | bool | Opt in to the process-kill remediation |
| `remediations.kill_runaway_process.cpu_threshold_percent` | float | Per-process CPU % that triggers a kill |
| `notifiers.console.enabled` | bool | Print alerts to stdout |
| `notifiers.slack.enabled` | bool | Send alerts to a Slack webhook |
| `notifiers.slack.webhook_url` | str | Required if Slack notifier is enabled — **never commit a real one** |
| `storage.db_path` | str | SQLite file path |
| `logging.level` | str | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `logging.log_path` | str | Rotating log file path (5MB per file, 3 backups) |

Config is validated on load — a bad threshold, malformed YAML, or a Slack notifier enabled without a webhook URL fails fast with a specific error message rather than silently falling back to a default.

## Fleet architecture (Phase 1: agent + Prometheus metrics)

Watchtower is being extended from a single-host tool into a fleet monitoring system:

```
Prometheus (scrapes) --> Agent 1 (/metrics, port 9100)
                     --> Agent 2 (/metrics, port 9100)
                     --> Agent N (/metrics, port 9100)
```

**What's implemented now:**
- `watchtower agent` — a thin process that runs checks on a background thread and exposes them at `/metrics` in real Prometheus exposition format (via the official `prometheus_client` library, not a hand-rolled format).
- `deploy/prometheus.yml` + `deploy/docker-compose.yml` — a local demo stack: one agent, scraped by Prometheus, visualized in Grafana.

**Try it:**
```bash
docker compose -f deploy/docker-compose.yml up
```
Then open:
- `http://localhost:9100/metrics` — raw metrics from the agent
- `http://localhost:9090` — Prometheus; try querying `watchtower_cpu_percent`
- `http://localhost:3000` — Grafana (login `admin` / `admin`); add Prometheus (`http://prometheus:9090`) as a data source and build a dashboard

**Not yet implemented (planned next phases):**
- Multiple real agents across different hosts (currently one agent, proving the pipeline)
- Alertmanager for alert deduplication/routing (the current single-host CLI still has the repeat-alert gap described in [Known limitations](#known-limitations))
- Centralized remediation dispatch back to a specific agent
- Kubernetes manifests (DaemonSet per node)

The single-host CLI (`watchtower run` / `check` / `serve`) still works exactly as before — the agent is an additional mode, not a replacement.

## Web dashboard



`watchtower serve` starts a small read-only Flask app:

- `/` — HTML dashboard showing current metric values and recent incidents
- `/api/status` — JSON endpoint with the same data
- `/healthz` — plain health check for load balancers / uptime monitors

It's deliberately read-only. There's no button to trigger a remediation from the web UI — exposing a "kill process" action behind a public URL is a bad idea, so that stays config/CLI-only.

## Deploying so it's viewable from your phone

The dashboard is a normal web app, so it's viewable from any device's browser — Android, iOS, desktop, doesn't matter. (Watchtower itself can't run natively as an app *on* a phone: it reads OS-level process/CPU/disk data and can kill processes, and both Android and iOS sandbox apps from doing that to the rest of the system. A browser hitting a URL is the correct way to view it on mobile, not a native install.)

**Free option: [Render](https://render.com)**

1. Push this repo to GitHub.
2. On Render: New → Blueprint → point at your repo. It will read [`render.yaml`](render.yaml) and configure itself.
3. Render builds and gives you a URL like `https://watchtower-xxxx.onrender.com`.
4. Open that URL on your phone. That's your dashboard, live, from a real deployed server.

Manual alternative (no blueprint):
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn -w 2 -b 0.0.0.0:$PORT wsgi:app`

Free-tier caveat: Render's free web services sleep after inactivity and take a few seconds to wake on the next request — mention this if you're demoing it live so it doesn't look broken.

## Testing

```bash
pytest --cov=watchtower --cov-report=term-missing
ruff check watchtower/ tests/
```

28 tests, covering:

- Breach/no-breach logic for every check type (mocked `psutil`, not dependent on the host's actual load)
- Config validation: missing file, malformed YAML, out-of-range thresholds, Slack enabled without a webhook
- **Remediation dry-run safety** — explicit tests asserting dry-run mode deletes zero files and terminates zero processes, and that real-run mode only touches what it's supposed to
- Storage read/write, including thread-safety (this caught a real bug during development — see below)
- Notifier failure handling (a failed Slack POST must not crash the monitor loop)
- Web dashboard routes and JSON API

**A bug the tests caught:** the original `Storage` implementation held one SQLite connection open for the object's lifetime. That works fine for the CLI (single-threaded) but broke the moment the multi-threaded Flask dashboard read from the same database a background loop was writing to — `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`. Fixed by opening a short-lived connection per call instead of one long-lived connection. Worth knowing this story if asked about testing/debugging in an interview — it's a genuine example of a concurrency bug found before it hit anything.

## Docker

```bash
docker build -t watchtower .
docker run -v $(pwd)/config.yaml:/app/config.yaml watchtower -c config.yaml run
```

Runs as a non-root user inside the container — a tool with process-kill and file-delete capabilities shouldn't run as root inside its own container by default.

## CI/CD

`.github/workflows/ci.yml` runs on every push and PR to `main`:

- Lint (`ruff`) and test (`pytest` with coverage) on Python 3.10, 3.11, and 3.12
- A separate job builds the Docker image to confirm it doesn't bit-rot

## Project structure

```
watchtower/
├── .github/workflows/ci.yml
├── config/config.example.yaml
├── tests/
│   ├── test_checks.py
│   ├── test_config.py
│   ├── test_notifiers.py
│   ├── test_remediation.py
│   ├── test_storage.py
│   └── test_web.py
├── watchtower/
│   ├── __init__.py
│   ├── checks.py
│   ├── cli.py
│   ├── config.py
│   ├── engine.py
│   ├── logging_setup.py
│   ├── notifiers.py
│   ├── remediation.py
│   ├── storage.py
│   └── web.py
├── Dockerfile
├── Procfile
├── render.yaml
├── wsgi.py
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## Known limitations

Be upfront about these if asked — knowing your project's limits is more credible than pretending it has none.

- **Single-host only.** It monitors the machine it runs on. Monitoring a fleet would need remote collection (SSH-based or an agent per host) — that's a materially different and harder problem than what's implemented here.
- **`KillRunawayProcess` accuracy.** `psutil.cpu_percent()` per-process needs a sampling interval to be accurate; a zero-interval call can misreport. Not a substitute for real resource limits (cgroups) in production.
- **SQLite, not a metrics backend.** Fine for one host's history; a real multi-host deployment would want Prometheus + node_exporter or similar, not this.
- **One alert channel implemented (Slack).** Adding another (email, PagerDuty, Discord) is a ~20-line `Notifier` subclass, but it's not done yet.
- **Free-tier hosting sleeps.** If deployed on Render's free tier, the dashboard cold-starts after inactivity.

## Possible extensions

If you want to keep building on this (and you should be able to explain any of these as "next steps I'd take" in an interview even if unbuilt):

- Remote host monitoring over SSH, with a `hosts.yaml` listing targets
- Additional notifiers (email via SMTP, PagerDuty)
- A `/metrics` endpoint in Prometheus exposition format
- Auth on the web dashboard before deploying anywhere long-term

## License

MIT — see [LICENSE](LICENSE).
