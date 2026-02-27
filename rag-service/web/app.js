const chatEl = document.getElementById("chat");
const formEl = document.getElementById("composer");
const qEl = document.getElementById("question");
const cEl = document.getElementById("collection");
const kEl = document.getElementById("topk");
const sendBtn = document.getElementById("sendBtn");

function addBubble(role, html) {
  const bubble = document.createElement("article");
  bubble.className = `bubble ${role}`;
  bubble.innerHTML = html;
  chatEl.appendChild(bubble);
  chatEl.scrollTop = chatEl.scrollHeight;
  return bubble;
}

function esc(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderSources(sources) {
  if (!Array.isArray(sources) || sources.length === 0) return "";
  const items = sources
    .map((s) => {
      const line =
        s.line_start != null
          ? ` (line ${s.line_start}${s.line_end && s.line_end !== s.line_start ? `-${s.line_end}` : ""})`
          : "";
      return `<li><strong>${esc(s.file)}</strong>${line}<br/>${esc(s.preview || "")}</li>`;
    })
    .join("");
  return `<div class="sources"><strong>Sources</strong><ul>${items}</ul></div>`;
}

async function ask(question) {
  const payload = {
    question,
    collection: cEl.value.trim() || "kb_docs",
    top_k: Number(kEl.value) || 4,
  };

  const resp = await fetch("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return await resp.json();
}

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = qEl.value.trim();
  if (!question) return;

  addBubble("user", `<div>${esc(question)}</div>`);
  qEl.value = "";
  sendBtn.disabled = true;

  const loading = addBubble("bot", "<div>Thinking...</div>");
  try {
    const data = await ask(question);
    const answer = esc(data.answer_text || data.answer || "");
    const meta = `<div class="meta">Confidence: ${esc(data.confidence || "N/A")} | Status: ${esc(data.status || "N/A")}</div>`;
    const src = renderSources(data.sources);
    loading.innerHTML = `<div>${answer}</div>${meta}${src}`;
  } catch (err) {
    loading.innerHTML = `<div>Error: ${esc(err.message)}</div>`;
  } finally {
    sendBtn.disabled = false;
    qEl.focus();
  }
});

addBubble(
  "bot",
  "Ready. Index your docs first, then ask questions. This chat uses <code>/query</code>."
);
