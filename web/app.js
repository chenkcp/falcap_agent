const chat = document.getElementById("chat");
const chatForm = document.getElementById("chatForm");
const promptEl = document.getElementById("prompt");
const sendBtn = document.getElementById("sendBtn");
const sessionBadge = document.getElementById("sessionBadge");

let sessionId = localStorage.getItem("falcap_phi_session_id") || null;
if (sessionId) {
  sessionBadge.textContent = `Session: ${sessionId.slice(0, 8)}`;
}

function addMessage(role, text) {
  const item = document.createElement("div");
  item.className = `msg ${role}`;
  item.textContent = text;
  chat.appendChild(item);
  chat.scrollTop = chat.scrollHeight;
  return item;
}

function isPipeDelimited(text) {
  const lines = text.split('\n').filter(l => l.trim());
  if (lines.length < 2) return false;
  return lines.some(line => line.includes('|'));
}

function parsePipeDelimitedTable(text) {
  const container = document.createElement("div");
  container.className = "table-container";
  
  const table = document.createElement("table");
  table.className = "pipe-table";
  
  const lines = text.split('\n').filter(l => l.trim());
  let isHeader = true;
  
  lines.forEach((line, idx) => {
    if (/^[\s|\-]+$/.test(line)) return;
    
    const cells = line.split('|').map(cell => cell.trim()).filter(cell => cell);
    if (cells.length === 0) return;
    
    if (isHeader && idx === 0) {
      const headerRow = document.createElement("tr");
      cells.forEach(cell => {
        const th = document.createElement("th");
        th.textContent = cell;
        headerRow.appendChild(th);
      });
      table.appendChild(headerRow);
      isHeader = false;
    } else {
      const row = document.createElement("tr");
      cells.forEach(cell => {
        const td = document.createElement("td");
        td.textContent = cell;
        row.appendChild(td);
      });
      table.appendChild(row);
    }
  });
  
  container.appendChild(table);
  return container;
}

async function sendMessageStream(message, onEvent) {
  const payload = { message, session_id: sessionId };

  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error("No response body from server");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    let lineBreak = buffer.indexOf("\n");
    while (lineBreak >= 0) {
      const rawLine = buffer.slice(0, lineBreak).trim();
      buffer = buffer.slice(lineBreak + 1);
      lineBreak = buffer.indexOf("\n");

      if (!rawLine) {
        continue;
      }

      onEvent(JSON.parse(rawLine));
    }
  }

  const tail = buffer.trim();
  if (tail) {
    onEvent(JSON.parse(tail));
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const text = promptEl.value.trim();
  if (!text) {
    return;
  }

  addMessage("user", text);
  promptEl.value = "";
  sendBtn.disabled = true;
  const assistantEl = addMessage("assistant", "");

  try {
    let fullText = "";
    await sendMessageStream(text, (eventData) => {
      if (eventData.type === "session" && eventData.session_id) {
        if (eventData.session_id !== sessionId) {
          sessionId = eventData.session_id;
          localStorage.setItem("falcap_phi_session_id", sessionId);
          sessionBadge.textContent = `Session: ${sessionId.slice(0, 8)}`;
        }
        return;
      }

      if (eventData.type === "delta") {
        fullText += eventData.text || "";
        // Convert to table if pipe-delimited, otherwise keep as text
        if (isPipeDelimited(fullText)) {
          assistantEl.innerHTML = "";
          assistantEl.appendChild(parsePipeDelimitedTable(fullText));
        } else {
          assistantEl.textContent = fullText;
        }
        chat.scrollTop = chat.scrollHeight;
        return;
      }

      if (eventData.type === "error") {
        assistantEl.textContent = `Request failed: ${eventData.error || "Unknown error"}`;
      }
    });

    if (!assistantEl.textContent.trim() && assistantEl.innerHTML.trim() === "") {
      assistantEl.textContent = "(No response)";
    }
  } catch (err) {
    assistantEl.textContent = `Request failed: ${err.message}`;
  } finally {
    sendBtn.disabled = false;
    promptEl.focus();
  }
});

addMessage(
  "assistant",
  "Falcap Phi is ready. Ask about work order audit readiness, process flow, or diagnostics."
);
