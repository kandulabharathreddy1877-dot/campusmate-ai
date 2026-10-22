// ---- Formatting helpers: bot text is escaped first, then simple formatting is added ----
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function inline(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s<)]+[^\s<).,;:!?])/g,
      (m, label, url1, url2) => {
        const url = url1 || url2;
        const text = label || url2;
        return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + text + "</a>";
      });
}

function renderBot(text) {
  const lines = escapeHtml(text).split("\n");
  let html = "";
  let inList = false;
  for (const raw of lines) {
    const bullet = raw.match(/^\s*[-*•]\s+(.*)$/);
    if (bullet) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += "<li>" + inline(bullet[1]) + "</li>";
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      if (raw.trim()) html += "<p>" + inline(raw) + "</p>";
    }
  }
  if (inList) html += "</ul>";
  return html;
}

// ---- UI ----
const log = document.getElementById("log");
const form = document.getElementById("composer");
const box = document.getElementById("question");
const sendBtn = document.getElementById("send");
const quickButtons = document.querySelectorAll("#quick button");
const chatHistory = [];
let busy = false;

function addMessage(kind, text) {
  const div = document.createElement("div");
  div.className = "msg " + kind;
  if (kind === "bot") div.innerHTML = renderBot(text);
  else div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function addTyping() {
  const div = document.createElement("div");
  div.className = "msg bot";
  div.innerHTML = '<span class="typing" aria-label="CampusMate AI is typing"><i></i><i></i><i></i></span>';
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function setBusy(state) {
  busy = state;
  sendBtn.disabled = state;
  quickButtons.forEach(b => (b.disabled = state));
}

async function ask(question) {
  question = question.trim();
  if (!question || busy) return;

  addMessage("user", question);
  box.value = "";
  box.style.height = "auto";
  setBusy(true);
  const typing = addTyping();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question, history: chatHistory.slice(-8) })
    });
    const data = await res.json().catch(() => ({}));
    typing.remove();

    if (res.ok && data.answer) {
      addMessage("bot", data.answer);
      chatHistory.push({ role: "user", content: question });
      chatHistory.push({ role: "assistant", content: data.answer });
    } else {
      addMessage("error", data.error || "Something went wrong. Please try again.");
    }
  } catch (err) {
    typing.remove();
    addMessage("error", "Could not reach the server. Check that the app is running, then try again.");
  } finally {
    setBusy(false);
    box.focus();
  }
}

form.addEventListener("submit", e => { e.preventDefault(); ask(box.value); });

box.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(box.value); }
});

box.addEventListener("input", () => {
  box.style.height = "auto";
  box.style.height = Math.min(box.scrollHeight, 128) + "px";
});

quickButtons.forEach(b => b.addEventListener("click", () => ask(b.dataset.q)));

// ---- Greeting + New chat ----
const GREETING = "Hi, I'm CampusMate AI. Ask me about MBU's courses, admissions, fees, placements or campus life. For official details, always confirm on the university website.";
function resetChat() {
  chatHistory.length = 0;
  log.innerHTML = "";
  addMessage("bot", GREETING);
  box.focus();
}
document.getElementById("newchat").addEventListener("click", resetChat);
addMessage("bot", GREETING);
