"""Minimal read-only web dashboard.

Exists for one reason: to make Watchtower viewable from a phone browser
when deployed to a cloud VM. It does not expose remediation controls -
this dashboard is intentionally read-only. Triggering a process kill from
a public URL would be a bad idea, so that stays CLI/config-only.
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template_string

from watchtower.checks import build_default_checks
from watchtower.config import AppConfig
from watchtower.storage import Storage

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Watchtower</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; max-width: 640px;
           margin: 2rem auto; padding: 0 1rem; background: #111; color: #eee; }
    h1 { font-size: 1.4rem; }
    .card { background: #1c1c1c; border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; }
    .ok { border-left: 4px solid #3fb950; }
    .breach { border-left: 4px solid #f85149; }
    .metric { font-size: 1.6rem; font-weight: 600; }
    .label { color: #999; font-size: 0.85rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    td, th { text-align: left; padding: 0.4rem; border-bottom: 1px solid #333; }
  </style>
</head>
<body>
  <h1>Watchtower</h1>
  <p class="label">Live host status, refreshed on page load.</p>
  {% for r in results %}
  <div class="card {{ 'breach' if r.breached else 'ok' }}">
    <div class="label">{{ r.name }}</div>
    <div class="metric">{{ "%.1f"|format(r.value) }}{{ ' procs' if r.name == 'process_count' else '%' }}</div>
    <div class="label">
      threshold: {{ "%.1f"|format(r.threshold) }} &middot;
      {{ 'BREACH' if r.breached else 'ok' }}
    </div>
  </div>
  {% endfor %}

  <h1>Recent incidents</h1>
  <table>
    <tr><th>Time (UTC)</th><th>Message</th></tr>
    {% for row in incidents %}
    <tr><td>{{ row['timestamp'] }}</td><td>{{ row['message'] }}</td></tr>
    {% else %}
    <tr><td colspan="2">No recorded incidents.</td></tr>
    {% endfor %}
  </table>

  <p class="label">JSON API: <a style="color:#6cb6ff" href="/api/status">/api/status</a></p>
</body>
</html>
"""


def create_app(config: AppConfig) -> Flask:
    app = Flask(__name__)
    checks = build_default_checks(config.thresholds)
    storage = Storage(config.storage["db_path"])

    def _current_results():
        results = []
        for check in checks:
            try:
                results.append(check.run())
            except Exception:
                continue
        return results

    @app.route("/")
    def dashboard():
        results = _current_results()
        incidents = storage.recent_incidents(limit=15)
        return render_template_string(PAGE_TEMPLATE, results=results, incidents=incidents)

    @app.route("/api/status")
    def api_status():
        results = _current_results()
        return jsonify({
            "dry_run": config.dry_run,
            "checks": [
                {
                    "name": r.name, "value": r.value, "threshold": r.threshold,
                    "breached": r.breached, "timestamp": r.timestamp,
                }
                for r in results
            ],
        })

    @app.route("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app
