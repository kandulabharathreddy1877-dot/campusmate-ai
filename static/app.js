const log = document.getElementById("log");
const form = document.getElementById("composer");
const box = document.getElementById("question");
const sendBtn = document.getElementById("send");
const quickButtons = document.querySelectorAll("#quick button");
const chatHistory = [];
let busy = false;

function escapeHtml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatInline(value) {
  return value
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s<)]+[^\s<).,;:!?])/g, (_, label, url1, url2) => {
      const url = url1 || url2;
      const text = label || url2;
      return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + text + '</a>';
    });
}

function renderBot(text) {
  const lines = escapeHtml(text).split("\n");
  let html = "";
  let inList = false;

  for (const raw of lines) {
    const bullet = raw.match(/^\s*[-*•]\s+(.*)$/);
    if (bullet) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += "<li>" + formatInline(bullet[1]) + "</li>";
    } else {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      if (raw.trim()) {
        html += "<p>" + formatInline(raw) + "</p>";
      }
    }
  }

  if (inList) html += "</ul>";
  return html;
}

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

async function readStreamingAnswer(response, message) {
  if (!response.body) {
    return { answer: "", error: "The server did not provide a response stream. Please try again." };
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let pendingData = [];
  let answer = "";
  let error = "";

  function dispatchEvent() {
    if (!pendingData.length) return;

    try {
      const event = JSON.parse(pendingData.join("\n"));
      if (event.error) {
        error = event.error;
      } else if (typeof event.text === "string") {
        answer += event.text;
        message.innerHTML = renderBot(answer);
        log.scrollTop = log.scrollHeight;
      }
    } catch {
      error = "The server sent an invalid response. Please try again.";
    }
    pendingData = [];
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop();

    for (const line of lines) {
      if (!line) dispatchEvent();
      else if (line.startsWith("data:")) pendingData.push(line.slice(5).trimStart());
    }

    if (done) {
      if (buffer) {
        if (buffer.startsWith("data:")) pendingData.push(buffer.slice(5).trimStart());
      }
      dispatchEvent();
      break;
    }
    if (error) {
      await reader.cancel();
      break;
    }
  }

  return { answer, error };
}

function setBusy(state) {
  busy = state;
  sendBtn.disabled = state;
  quickButtons.forEach((button) => {
    button.disabled = state;
  });
}

async function ask(question) {
  const trimmed = question.trim();
  if (!trimmed || busy) return;

  addMessage("user", trimmed);
  box.value = "";
  box.style.height = "auto";
  setBusy(true);
  const typing = addTyping();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: trimmed, history: chatHistory.slice(-4) })
    });

    if (response.ok && response.headers.get("content-type")?.includes("text/event-stream")) {
      typing.remove();
      const botMessage = addMessage("bot", "");
      const result = await readStreamingAnswer(response, botMessage);
      if (result.answer && !result.error) {
        chatHistory.push({ role: "user", content: trimmed });
        chatHistory.push({ role: "assistant", content: result.answer });
      }
      if (result.error) addMessage("error", result.error);
      else if (!result.answer) addMessage("error", "The AI service sent an empty reply. Try again.");
    } else {
      const data = await response.json().catch(() => ({}));
      typing.remove();

      if (response.ok && data.answer) {
        addMessage("bot", data.answer);
        chatHistory.push({ role: "user", content: trimmed });
        chatHistory.push({ role: "assistant", content: data.answer });
      } else {
        addMessage("error", data.error || "Something went wrong. Please try again.");
      }
    }
  } catch (error) {
    typing.remove();
    addMessage("error", "Could not reach the server. Check that the app is running, then try again.");
  } finally {
    setBusy(false);
    box.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(box.value);
});

box.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    ask(box.value);
  }
});

box.addEventListener("input", () => {
  box.style.height = "auto";
  box.style.height = Math.min(box.scrollHeight, 128) + "px";
});

quickButtons.forEach((button) => {
  button.addEventListener("click", () => ask(button.dataset.q));
});

const GREETING = "Hi, I'm CampusMate AI. Ask me about MBU's courses, admissions, fees, placements or campus life. For official details, always confirm on the university website.";
function resetChat() {
  chatHistory.length = 0;
  log.innerHTML = "";
  addMessage("bot", GREETING);
  box.focus();
}

document.getElementById("newchat").addEventListener("click", resetChat);

const settingsDialog = document.getElementById("settings-dialog");
const settingsForm = document.getElementById("settings-form");
const settingsStatus = document.getElementById("settings-status");
const apiKeyInput = document.getElementById("api-key");
const settingsSave = document.getElementById("settings-save");
const isLocalSite = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
document.getElementById("settings-button").hidden = !isLocalSite;

document.getElementById("settings-button").addEventListener("click", async () => {
  settingsStatus.textContent = "Checking local settings…";
  settingsDialog.showModal();
  try {
    const response = await fetch("/api/settings");
    const data = await response.json().catch(() => ({}));
    settingsStatus.textContent = response.status === 404
      ? "Restart the server and refresh this page to enable settings."
      : response.ok
      ? (data.api_key_configured ? "A key is saved locally. Enter a new key to replace it." : "No key is saved yet.")
      : (data.error || "Could not check settings.");
  } catch {
    settingsStatus.textContent = "Could not reach the local server.";
  }
  apiKeyInput.focus();
});

document.getElementById("settings-close").addEventListener("click", () => {
  settingsDialog.close();
  settingsForm.reset();
});

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  settingsSave.disabled = true;
  settingsStatus.textContent = "Saving key locally…";
  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKeyInput.value })
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 404) {
      settingsStatus.textContent = "Restart the server and refresh this page to enable settings.";
      return;
    }
    if (!response.ok) {
      settingsStatus.textContent = data.error || "Could not save the key.";
      return;
    }
    settingsForm.reset();
    settingsStatus.textContent = "Key saved in .env. You can try chatting now.";
  } catch {
    settingsStatus.textContent = "Could not reach the local server. The key was not confirmed as saved.";
  } finally {
    settingsSave.disabled = false;
  }
});

addMessage("bot", GREETING);
