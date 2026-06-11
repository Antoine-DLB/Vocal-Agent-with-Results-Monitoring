// Dashboard logic: fetch stats + logs from the FastAPI backend, render the
// stat cards, a score-over-time line chart, and the recent-interactions table.

const REFRESH_MS = 10_000;
let scoreChart = null;

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function truncate(text, max = 60) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}

function renderStats(stats) {
  document.getElementById("stat-total").textContent = stats.total_interactions ?? 0;
  document.getElementById("stat-score").textContent =
    (stats.avg_overall_score ?? 0).toFixed(2);
  document.getElementById("stat-latency").textContent =
    Math.round(stats.avg_latency_llm_ms ?? 0) + " ms";
}

function renderChart(scoreOverTime) {
  const labels = scoreOverTime.map((p) => fmtTime(p.timestamp));
  const data = scoreOverTime.map((p) => p.overall);
  const ctx = document.getElementById("scoreChart");

  if (scoreChart) {
    scoreChart.data.labels = labels;
    scoreChart.data.datasets[0].data = data;
    scoreChart.update();
    return;
  }

  scoreChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Overall score",
        data,
        borderColor: "#ff7a59",
        backgroundColor: "rgba(255,122,89,0.15)",
        tension: 0.3,
        fill: true,
        pointRadius: 4,
      }],
    },
    options: {
      responsive: true,
      scales: {
        y: { min: 0, max: 5, ticks: { stepSize: 1, color: "#8b90a3" }, grid: { color: "#2a2e3c" } },
        x: { ticks: { color: "#8b90a3", maxRotation: 0, autoSkip: true }, grid: { color: "#2a2e3c" } },
      },
      plugins: { legend: { labels: { color: "#e6e8ef" } } },
    },
  });
}

function renderTable(logs) {
  const rows = document.getElementById("rows");
  const recent = logs.slice(-10).reverse();

  if (recent.length === 0) {
    rows.innerHTML = '<tr><td colspan="5" class="muted">No interactions yet.</td></tr>';
    return;
  }

  rows.innerHTML = recent.map((entry) => {
    const scores = entry.scores || {};
    const flags = (scores.flags || [])
      .map((f) => `<span class="badge">${f}</span>`)
      .join("") || '<span class="muted">—</span>';
    const llmMs = (entry.latency || {}).llm_ms ?? "—";
    return `
      <tr>
        <td class="muted">${fmtTime(entry.timestamp)}</td>
        <td class="q" title="${(entry.transcript || "").replace(/"/g, "&quot;")}">${truncate(entry.transcript)}</td>
        <td class="score">${scores.overall ?? "—"}</td>
        <td>${flags}</td>
        <td>${llmMs} ms</td>
      </tr>`;
  }).join("");
}

async function refresh() {
  try {
    const [statsRes, logsRes] = await Promise.all([
      fetch("/api/stats"),
      fetch("/api/logs"),
    ]);
    const stats = await statsRes.json();
    const logs = await logsRes.json();

    renderStats(stats);
    renderChart(stats.score_over_time || []);
    renderTable(logs);
  } catch (err) {
    console.error("Dashboard refresh failed:", err);
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
