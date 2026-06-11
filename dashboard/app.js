// Dashboard + voice chat logic.
//
//  - Chat: hold the mic button (or Space), record via MediaRecorder, release to
//    POST the audio to /api/chat, then render the answer and play it back.
//  - Monitoring: poll /api/stats and /api/logs to render the stat cards, the
//    score-over-time chart and the recent-interactions table.

const REFRESH_MS = 10_000;
let scoreChart = null;

// --------------------------------------------------------------------------- //
// Helpers                                                                     //
// --------------------------------------------------------------------------- //
function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function truncate(text, max = 60) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

// --------------------------------------------------------------------------- //
// Voice chat                                                                  //
// --------------------------------------------------------------------------- //
const micBtn = document.getElementById("micBtn");
const statusEl = document.getElementById("status");
const threadEl = document.getElementById("thread");

let mediaRecorder = null;
let mediaStream = null;
let chunks = [];
let isRecording = false;
let isBusy = false;

function setStatus(msg) {
  statusEl.textContent = msg;
}

async function startRecording() {
  if (isRecording || isBusy) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus("This browser does not support microphone capture.");
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    setStatus("Microphone access denied.");
    return;
  }
  chunks = [];
  mediaRecorder = new MediaRecorder(mediaStream);
  mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
  mediaRecorder.onstop = sendAudio;
  mediaRecorder.start();
  isRecording = true;
  micBtn.classList.add("recording");
  setStatus("Listening… release to send.");
}

function stopRecording() {
  if (!isRecording) return;
  isRecording = false;
  micBtn.classList.remove("recording");
  setStatus("Processing…");
  if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
}

function releaseMic() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
}

async function sendAudio() {
  releaseMic();
  const blob = new Blob(chunks, { type: "audio/webm" });
  if (blob.size === 0) { setStatus("Nothing recorded. Try again."); return; }

  isBusy = true;
  micBtn.disabled = true;
  try {
    const form = new FormData();
    form.append("audio", blob, "audio.webm");
    const res = await fetch("/api/chat", { method: "POST", body: form });
    const data = await res.json();

    if (!res.ok) {
      setStatus(data.error || "Something went wrong.");
      return;
    }
    renderTurn(data);
    playAudio(data.audio, data.audio_mime);
    setStatus("Ready.");
    refresh(); // monitoring reflects the new interaction immediately
  } catch (err) {
    console.error(err);
    setStatus("Request failed. Is the server running?");
  } finally {
    isBusy = false;
    micBtn.disabled = false;
  }
}

function playAudio(b64, mime) {
  if (!b64) return null;
  const audio = new Audio(`data:${mime || "audio/mpeg"};base64,${b64}`);
  audio.play().catch(() => {});
  return audio;
}

function clearEmptyThread() {
  const empty = threadEl.querySelector(".empty-thread");
  if (empty) empty.remove();
}

function renderTurn(data) {
  clearEmptyThread();

  const user = document.createElement("div");
  user.className = "bubble user";
  user.innerHTML = `<div class="who">You</div>${escapeHtml(data.transcript)}`;

  const s = data.scores || {};
  const flags = (s.flags || []).map((f) => `<span class="badge">${escapeHtml(f)}</span>`).join("");
  const llmMs = (data.latency || {}).llm_ms ?? "—";

  const coach = document.createElement("div");
  coach.className = "bubble coach";
  coach.innerHTML =
    `<div class="who">Coach</div>${escapeHtml(data.response)}` +
    `<div class="meta">` +
      `<span>⭐ overall ${s.overall ?? "—"}/5</span>` +
      `<span>· relevance ${s.relevance ?? "—"} · concision ${s.concision ?? "—"} · tone ${s.tone ?? "—"}</span>` +
      `<span>· ${llmMs} ms</span>` +
      (flags ? `<span>${flags}</span>` : "") +
      `<button class="replay">▶ replay</button>` +
    `</div>`;

  coach.querySelector(".replay").addEventListener("click", () => playAudio(data.audio, data.audio_mime));

  threadEl.appendChild(user);
  threadEl.appendChild(coach);
  coach.scrollIntoView({ behavior: "smooth", block: "end" });
}

// Mouse / touch: hold to talk.
micBtn.addEventListener("pointerdown", (e) => { e.preventDefault(); startRecording(); });
micBtn.addEventListener("pointerup", (e) => { e.preventDefault(); stopRecording(); });
micBtn.addEventListener("pointerleave", () => stopRecording());
micBtn.addEventListener("pointercancel", () => stopRecording());

// Keyboard: hold Space to talk (ignored while typing in a field).
document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !e.repeat && e.target === document.body) {
    e.preventDefault();
    startRecording();
  }
});
document.addEventListener("keyup", (e) => {
  if (e.code === "Space" && e.target === document.body) {
    e.preventDefault();
    stopRecording();
  }
});

// --------------------------------------------------------------------------- //
// Monitoring                                                                  //
// --------------------------------------------------------------------------- //
function renderStats(stats) {
  document.getElementById("stat-total").textContent = stats.total_interactions ?? 0;
  document.getElementById("stat-score").textContent = (stats.avg_overall_score ?? 0).toFixed(2);
  document.getElementById("stat-latency").textContent = Math.round(stats.avg_latency_llm_ms ?? 0) + " ms";
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
    const flags = (scores.flags || []).map((f) => `<span class="badge">${escapeHtml(f)}</span>`).join("")
      || '<span class="muted">—</span>';
    const llmMs = (entry.latency || {}).llm_ms ?? "—";
    return `
      <tr>
        <td class="muted">${fmtTime(entry.timestamp)}</td>
        <td class="q" title="${escapeHtml(entry.transcript)}">${escapeHtml(truncate(entry.transcript))}</td>
        <td class="score">${scores.overall ?? "—"}</td>
        <td>${flags}</td>
        <td>${llmMs} ms</td>
      </tr>`;
  }).join("");
}

async function refresh() {
  try {
    const [statsRes, logsRes] = await Promise.all([fetch("/api/stats"), fetch("/api/logs")]);
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
