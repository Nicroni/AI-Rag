const channelEl = document.getElementById("channel");
const hoursEl = document.getElementById("hours");
const eventIdsEl = document.getElementById("eventIds");
const levelsEl = document.getElementById("levels");
const maxEventsEl = document.getElementById("maxEvents");
const loadBtn = document.getElementById("loadBtn");
const eventsEl = document.getElementById("events");
const statsEl = document.getElementById("stats");
const qEl = document.getElementById("question");
const analyzeBtn = document.getElementById("analyzeBtn");
const exportJsonBtn = document.getElementById("exportJsonBtn");
const exportMdBtn = document.getElementById("exportMdBtn");
const structuredEl = document.getElementById("structured");
const answerEl = document.getElementById("answer");
let lastLogQuery = null;
let lastAnalysis = null;

function parseNums(v) {
  return String(v || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean)
    .map((x) => Number(x))
    .filter((x) => Number.isFinite(x));
}

function esc(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function loadChannels() {
  const r = await fetch("/windows-logs/channels");
  const d = await r.json();
  channelEl.innerHTML = "";
  (d.channels || []).forEach((c) => {
    const o = document.createElement("option");
    o.value = c;
    o.textContent = c;
    channelEl.appendChild(o);
  });
}

function payload() {
  return {
    channel: channelEl.value,
    hours_back: Number(hoursEl.value) || 2,
    event_ids: parseNums(eventIdsEl.value),
    levels: parseNums(levelsEl.value),
    max_events: Number(maxEventsEl.value) || 50,
  };
}

async function queryLogs() {
  const r = await fetch("/windows-logs/query", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload()),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
  lastLogQuery = d;
  return d;
}

function renderEvents(events) {
  eventsEl.innerHTML = "";
  if (!events.length) {
    eventsEl.innerHTML = `<div class="event muted">No events in selected window.</div>`;
    return;
  }
  events.forEach((e) => {
    const div = document.createElement("div");
    div.className = "event";
    div.innerHTML = `
      <div class="meta">${esc(e.TimeCreated)} | ID ${esc(e.Id)} | ${esc(e.LevelDisplayName)} | ${esc(e.ProviderName)}</div>
      <div class="msg">${esc(e.Message || "")}</div>
    `;
    eventsEl.appendChild(div);
  });
}

async function analyze() {
  const body = {
    ...payload(),
    question: qEl.value.trim(),
  };
  if (!body.question) return;
  const r = await fetch("/windows-logs/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
  lastAnalysis = d;
  renderStructured(d.sections || {});
  answerEl.textContent = d.answer || "";
}

function renderStructured(sections) {
  const map = [
    ["Root Cause", sections.root_cause || []],
    ["Evidence", sections.evidence || []],
    ["Actions", sections.actions || []],
    ["Risk", sections.risk || []],
  ];
  structuredEl.innerHTML = map
    .map(([title, items]) => {
      const list = items.length
        ? `<ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
        : `<div class="muted">No data</div>`;
      return `<div class="card"><h4>${esc(title)}</h4>${list}</div>`;
    })
    .join("");
}

function downloadFile(name, text, contentType) {
  const blob = new Blob([text], { type: contentType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function buildIncidentReport() {
  const now = new Date().toISOString();
  return {
    generated_at: now,
    filters: payload(),
    question: qEl.value.trim(),
    log_query: lastLogQuery,
    analysis: lastAnalysis,
  };
}

function reportToMarkdown(rep) {
  const s = (rep.analysis && rep.analysis.sections) || {};
  const lines = [];
  lines.push(`# Incident Report`);
  lines.push(`- Generated: ${rep.generated_at}`);
  lines.push(`- Channel: ${rep.filters.channel}`);
  lines.push(`- Hours Back: ${rep.filters.hours_back}`);
  lines.push(`- Event IDs: ${(rep.filters.event_ids || []).join(", ") || "N/A"}`);
  lines.push(`- Levels: ${(rep.filters.levels || []).join(", ") || "N/A"}`);
  lines.push(`- Max Events: ${rep.filters.max_events}`);
  lines.push(``);
  lines.push(`## Question`);
  lines.push(rep.question || "N/A");
  lines.push(``);
  lines.push(`## Root Cause`);
  (s.root_cause || ["N/A"]).forEach((x) => lines.push(`- ${x}`));
  lines.push(``);
  lines.push(`## Evidence`);
  (s.evidence || ["N/A"]).forEach((x) => lines.push(`- ${x}`));
  lines.push(``);
  lines.push(`## Actions`);
  (s.actions || ["N/A"]).forEach((x) => lines.push(`- ${x}`));
  lines.push(``);
  lines.push(`## Risk`);
  (s.risk || ["N/A"]).forEach((x) => lines.push(`- ${x}`));
  lines.push(``);
  lines.push(`## Raw Answer`);
  lines.push((rep.analysis && rep.analysis.answer) || "N/A");
  return lines.join("\n");
}

loadBtn.addEventListener("click", async () => {
  loadBtn.disabled = true;
  try {
    const d = await queryLogs();
    statsEl.textContent = `Channel: ${d.channel} | Hours: ${d.hours_back} | Events: ${d.count}`;
    renderEvents(d.events || []);
  } catch (e) {
    statsEl.textContent = `Error: ${e.message}`;
    renderEvents([]);
  } finally {
    loadBtn.disabled = false;
  }
});

analyzeBtn.addEventListener("click", async () => {
  analyzeBtn.disabled = true;
  answerEl.textContent = "Analyzing...";
  try {
    await analyze();
  } catch (e) {
    answerEl.textContent = `Error: ${e.message}`;
  } finally {
    analyzeBtn.disabled = false;
  }
});

exportJsonBtn.addEventListener("click", () => {
  if (!lastAnalysis) {
    answerEl.textContent = "Run Analyze first.";
    return;
  }
  const rep = buildIncidentReport();
  downloadFile(`incident_report_${Date.now()}.json`, JSON.stringify(rep, null, 2), "application/json");
});

exportMdBtn.addEventListener("click", () => {
  if (!lastAnalysis) {
    answerEl.textContent = "Run Analyze first.";
    return;
  }
  const rep = buildIncidentReport();
  downloadFile(`incident_report_${Date.now()}.md`, reportToMarkdown(rep), "text/markdown");
});

(async () => {
  await loadChannels();
  await loadBtn.click();
})();
