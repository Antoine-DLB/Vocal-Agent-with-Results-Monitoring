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

// Lightweight, safe formatter: escapes first, then renders paragraphs, bullet /
// numbered lists and **bold** so multi-point answers are readable instead of one
// dense block.
function inlineMd(s) {
  return s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function formatResponse(text) {
  const safe = escapeHtml(text || "");
  const lines = safe.split(/\r?\n/);
  let html = "";
  let list = null; // "ul" | "ol" | null
  const closeList = () => { if (list) { html += `</${list}>`; list = null; } };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { closeList(); continue; }

    const ul = line.match(/^[-*•]\s+(.*)$/);
    const ol = line.match(/^\d+[.)]\s+(.*)$/);
    if (ul) {
      if (list !== "ul") { closeList(); html += "<ul>"; list = "ul"; }
      html += `<li>${inlineMd(ul[1])}</li>`;
    } else if (ol) {
      if (list !== "ol") { closeList(); html += "<ol>"; list = "ol"; }
      html += `<li>${inlineMd(ol[1])}</li>`;
    } else {
      closeList();
      html += `<p>${inlineMd(line)}</p>`;
    }
  }
  closeList();
  return html || `<p>${safe}</p>`;
}

// --------------------------------------------------------------------------- //
// Voice chat                                                                  //
// --------------------------------------------------------------------------- //
const micBtn = document.getElementById("micBtn");
const statusEl = document.getElementById("status");
const threadEl = document.getElementById("thread");

let mediaRecorder = null;
let mediaStream = null;       // kept alive after the first grant for instant restarts
let chunks = [];
let active = false;           // user is currently holding the mic / Space
let recorderReady = false;    // MediaRecorder is actually running
let isBusy = false;           // a turn is being processed by the server

function setStatus(msg) {
  statusEl.textContent = msg;
}

// Acquire the mic stream once and reuse it. Awaiting getUserMedia on every
// press caused a race: a quick click resolved *after* release, so recording
// started but was never stopped. Reusing the stream makes restarts synchronous.
async function ensureStream() {
  if (mediaStream) return mediaStream;
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("getUserMedia unavailable (needs http://localhost or HTTPS)");
  }
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  return mediaStream;
}

function startRecorder() {
  chunks = [];
  const opts =
    window.MediaRecorder && MediaRecorder.isTypeSupported &&
    MediaRecorder.isTypeSupported("audio/webm")
      ? { mimeType: "audio/webm" }
      : {};
  mediaRecorder = new MediaRecorder(mediaStream, opts);
  mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
  mediaRecorder.onstop = onRecordingStopped;
  mediaRecorder.start();
  recorderReady = true;
}

async function beginTalk() {
  if (isBusy || active) return;
  active = true;
  micBtn.classList.add("recording");

  if (!mediaStream) {
    setStatus("Requesting microphone…");
    try {
      await ensureStream();
    } catch (err) {
      console.error("[mic] getUserMedia failed:", err);
      setStatus("Microphone blocked. Allow access and open http://localhost:8000.");
      active = false;
      micBtn.classList.remove("recording");
      return;
    }
    if (!active) {
      // Released during the permission prompt: keep the stream for next time.
      setStatus("Mic ready — hold the mic (or Space) and speak.");
      micBtn.classList.remove("recording");
      return;
    }
  }

  startRecorder();
  setStatus("Listening… release to send.");
}

function endTalk() {
  if (!active) return;
  active = false;
  micBtn.classList.remove("recording");

  if (recorderReady && mediaRecorder && mediaRecorder.state !== "inactive") {
    recorderReady = false;
    setStatus("Processing…");
    mediaRecorder.stop(); // fires onstop -> onRecordingStopped
  } else {
    // Recorder had not actually started yet (released too fast).
    setStatus("Ready.");
  }
}

async function onRecordingStopped() {
  const blob = new Blob(chunks, { type: (mediaRecorder && mediaRecorder.mimeType) || "audio/webm" });
  if (blob.size === 0) { setStatus("Nothing recorded — hold a bit longer."); return; }

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
    console.error("[chat] request failed:", err);
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
    `<div class="who">Coach</div><div class="text">${formatResponse(data.response)}</div>` +
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

// Mouse / touch: hold to talk. Pointer capture keeps pointerup targeted at the
// button even if the cursor drifts off it while holding.
micBtn.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  try { micBtn.setPointerCapture(e.pointerId); } catch (_) {}
  beginTalk();
});
micBtn.addEventListener("pointerup", (e) => { e.preventDefault(); endTalk(); });
micBtn.addEventListener("pointercancel", () => endTalk());

// Keyboard: hold Space to talk (ignored while typing in a field).
const isTypingTarget = (el) =>
  el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);

document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !e.repeat && !isTypingTarget(e.target)) {
    e.preventDefault();
    beginTalk();
  }
});
document.addEventListener("keyup", (e) => {
  if (e.code === "Space" && !isTypingTarget(e.target)) {
    e.preventDefault();
    endTalk();
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
      maintainAspectRatio: false,
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

// --------------------------------------------------------------------------- //
// Sidebar navigation (Coach / Monitoring) + collapse                          //
// --------------------------------------------------------------------------- //
const sidebar = document.getElementById("sidebar");
const collapseBtn = document.getElementById("collapseBtn");
const navItems = document.querySelectorAll(".nav-item");
const views = {
  coach: document.getElementById("view-coach"),
  monitoring: document.getElementById("view-monitoring"),
};

function showView(name) {
  if (!views[name]) name = "coach";
  for (const [key, el] of Object.entries(views)) el.hidden = key !== name;
  navItems.forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  localStorage.setItem("view", name);
  if (name === "monitoring") {
    // The chart may have been created while hidden (0 size) — refit it.
    refresh().then(() => { if (scoreChart) scoreChart.resize(); });
  }
}

navItems.forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));

function setCollapsed(collapsed) {
  sidebar.classList.toggle("collapsed", collapsed);
  collapseBtn.textContent = collapsed ? "»" : "«";
  localStorage.setItem("collapsed", collapsed ? "true" : "false");
}
collapseBtn.addEventListener("click", () => setCollapsed(!sidebar.classList.contains("collapsed")));

// Restore persisted UI state.
setCollapsed(localStorage.getItem("collapsed") === "true");
showView(localStorage.getItem("view") || "coach");
