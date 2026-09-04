"""Read-only web dashboard with live trend charts.

Exists to make Watchtower viewable from a phone browser when deployed to
a cloud host. Deliberately read-only - no remediation controls here;
triggering a process kill from a public URL would be a bad idea, so that
stays CLI/config-only.

Every hit to `/` or `/api/status` records a check result to storage. This
is what feeds the trend charts: each page load or auto-refresh poll is
itself a new data point, so a dashboard left open for a while naturally
builds up its own history without needing a separate `watchtower run`
process running alongside it.
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template_string, request

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
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      max-width: 720px; margin: 0 auto; padding: 1.5rem 1rem 3rem;
      background: #0d0d0f; color: #e8e8ea;
    }
    h1 { font-size: 1.3rem; margin: 0 0 0.2rem; letter-spacing: -0.01em; }
    .subtitle { color: #8a8a92; font-size: 0.82rem; margin-bottom: 1.4rem; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.7rem; margin-bottom: 1.8rem; }
    @media (max-width: 480px) { .grid { grid-template-columns: 1fr; } }
    .card {
      background: #17171a; border-radius: 10px; padding: 0.9rem 1rem;
      border-left: 4px solid var(--accent, #3fb950);
      transition: border-color 0.4s ease;
    }
    .card-top { display: flex; justify-content: space-between; align-items: baseline; }
    .name { color: #9a9aa2; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
    .trend { font-size: 0.78rem; font-variant-numeric: tabular-nums; }
    .trend.up { color: #f0883e; }
    .trend.down { color: #3fb950; }
    .trend.flat { color: #6a6a72; }
    .value {
      font-size: 1.9rem; font-weight: 650;
      font-variant-numeric: tabular-nums; margin: 0.1rem 0 0.15rem;
    }
    .meta { color: #8a8a92; font-size: 0.76rem; }
    .status-tag { font-weight: 600; }
    canvas.spark { width: 100%; height: 34px; margin-top: 0.4rem; }
    h2 { font-size: 1.02rem; margin: 0 0 0.6rem; color: #d5d5d8; }
    table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
    td, th { text-align: left; padding: 0.45rem 0.3rem; border-bottom: 1px solid #232326; }
    th { color: #8a8a92; font-weight: 500; }
    .footer-link { color: #6cb6ff; text-decoration: none; }
    .live-dot {
      display: inline-block; width: 7px; height: 7px; border-radius: 50%;
      background: #3fb950; margin-right: 5px; animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
  </style>
</head>
<body>
  <h1>Watchtower</h1>
  <p class="subtitle"><span class="live-dot"></span>Live &middot; auto-refreshing every 5s</p>

  <div class="grid" id="cards"></div>

  <h2>Recent incidents</h2>
  <table>
    <tr><th>Time (UTC)</th><th>Message</th></tr>
    {% for row in incidents %}
    <tr><td>{{ row['timestamp'] }}</td><td>{{ row['message'] }}</td></tr>
    {% else %}
    <tr><td colspan="2">No recorded incidents.</td></tr>
    {% endfor %}
  </table>

  <p class="subtitle" style="margin-top:1.4rem">
    JSON API: <a class="footer-link" href="/api/status">/api/status</a>
  </p>

<script>
const CHECK_META = {
  cpu:           { label: "CPU",       unit: "%",     color: "#58a6ff" },
  memory:        { label: "Memory",    unit: "%",     color: "#bc8cff" },
  disk:          { label: "Disk",      unit: "%",     color: "#f0883e" },
  process_count: { label: "Processes", unit: " procs", color: "#3fb950" },
};

const state = {};   // name -> { history: [values...], charted values }
const charts = {};  // name -> Chart.js instance

function colorFor(ratio) {
  // ratio = value / threshold. Green well under, amber approaching, red breached.
  if (ratio >= 1) return "#f85149";
  if (ratio >= 0.8) return "#f0883e";
  return "#3fb950";
}

function renderCards(checks) {
  const grid = document.getElementById("cards");
  grid.innerHTML = "";

  for (const c of checks) {
    const meta = CHECK_META[c.name] || { label: c.name, unit: "", color: "#58a6ff" };
    const ratio = c.threshold > 0 ? c.value / c.threshold : 0;
    const accent = colorFor(ratio);

    if (!state[c.name]) state[c.name] = { history: [] };
    const hist = state[c.name].history;
    hist.push(c.value);
    if (hist.length > 60) hist.shift();

    const prev = hist.length > 6 ? hist[hist.length - 6] : hist[0];
    const delta = c.value - prev;
    let trendClass = "flat", trendSymbol = "→";
    if (delta > 0.5) { trendClass = "up"; trendSymbol = "↑"; }
    else if (delta < -0.5) { trendClass = "down"; trendSymbol = "↓"; }

    const card = document.createElement("div");
    card.className = "card";
    card.style.setProperty("--accent", accent);
    card.innerHTML = `
      <div class="card-top">
        <span class="name">${meta.label}</span>
        <span class="trend ${trendClass}">${trendSymbol} ${Math.abs(delta).toFixed(1)}</span>
      </div>
      <div class="value">${c.value.toFixed(1)}${meta.unit}</div>
      <div class="meta">
        threshold ${c.threshold.toFixed(0)}${meta.unit} &middot;
        <span class="status-tag" style="color:${accent}">${c.breached ? "BREACH" : "ok"}</span>
      </div>
      <canvas class="spark" id="chart-${c.name}"></canvas>
    `;
    grid.appendChild(card);

    requestAnimationFrame(() => {
      const ctx = document.getElementById(`chart-${c.name}`);
      if (!ctx) return;
      if (charts[c.name]) {
        charts[c.name].data.labels = hist.map((_, i) => i);
        charts[c.name].data.datasets[0].data = hist;
        charts[c.name].update("none");
        return;
      }
      charts[c.name] = new Chart(ctx, {
        type: "line",
        data: {
          labels: hist.map((_, i) => i),
          datasets: [{
            data: hist, borderColor: meta.color, borderWidth: 1.5,
            pointRadius: 0, tension: 0.3, fill: false,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          scales: { x: { display: false }, y: { display: false } },
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
        },
      });
    });
  }
}

async function seedHistory() {
  for (const name of Object.keys(CHECK_META)) {
    try {
      const resp = await fetch(`/api/history?name=${name}&limit=60`);
      const data = await resp.json();
      state[name] = { history: data.values || [] };
    } catch (e) { /* ignore - falls back to building history live */ }
  }
}

async function poll() {
  try {
    const resp = await fetch("/api/status");
    const data = await resp.json();
    renderCards(data.checks);
  } catch (e) {
    console.error("poll failed", e);
  }
}

(async () => {
  await seedHistory();
  await poll();
  setInterval(poll, 5000);
})();
</script>
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
                result = check.run()
            except Exception:
                continue
            results.append(result)
            storage.record_check(result)
        return results

    @app.route("/")
    def dashboard():
        _current_results()  # populate storage so the first chart render has data
        incidents = storage.recent_incidents(limit=15)
        return render_template_string(PAGE_TEMPLATE, incidents=incidents)

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

    @app.route("/api/history")
    def api_history():
        name = request.args.get("name", "")
        limit = min(int(request.args.get("limit", 60)), 200)
        rows = storage.history(name, limit=limit)
        return jsonify({
            "name": name,
            "timestamps": [r["timestamp"] for r in rows],
            "values": [r["value"] for r in rows],
        })

    @app.route("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app
