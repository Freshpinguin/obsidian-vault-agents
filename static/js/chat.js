import { state } from "./state.js";
import { postChatMessage, deleteSession } from "./api.js";
import { renderMarkdown } from "./markdown.js";
import { showToast } from "./toast.js";
import { loadFileContent } from "./viewer.js";
import { loadFileTree, renderTree } from "./tree.js";
import {
  messagesEl,
  chatFormEl,
  messageInputEl,
  sendBtnEl,
  newChatBtn,
  explorerSearchInput,
  emptyStateEl,
  fileContainerEl,
} from "./dom.js";

// ==========================================
// 7. Chat functionality
// ==========================================
export function addChatMessage(role, text) {
  const item = document.createElement("div");
  item.className = `msg-item ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  if (role === "assistant") {
    bubble.innerHTML = renderMarkdown(text);
    // Wikilinks in Agenten-Antworten klickbar machen
    bubble.querySelectorAll(".wikilink").forEach(linkEl => {
      linkEl.addEventListener("click", (e) => {
        e.preventDefault();
        const target = linkEl.getAttribute("data-wikilink");
        if (target) loadFileContent(target);
      });
    });
  } else {
    bubble.textContent = text;
  }

  item.appendChild(bubble);
  messagesEl.appendChild(item);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return item;
}

export function autoResizeTextarea() {
  messageInputEl.style.height = "auto";
  messageInputEl.style.height = Math.min(messageInputEl.scrollHeight, 140) + "px";
}

if (messageInputEl) {
  messageInputEl.addEventListener("input", autoResizeTextarea);
}

export async function sendChatMessage(text) {
  state.isSending = true;
  sendBtnEl.disabled = true;

  // Thinking Indicator
  const thinkingEl = document.createElement("div");
  thinkingEl.className = "msg-item assistant";
  thinkingEl.innerHTML = `
    <div class="thinking-indicator">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
      <span class="thinking-text">Chat assistant is thinking…</span>
      <div class="thinking-dots">
        <div class="thinking-dot"></div>
        <div class="thinking-dot"></div>
        <div class="thinking-dot"></div>
      </div>
    </div>
  `;
  messagesEl.appendChild(thinkingEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  const thinkingTextEl = thinkingEl.querySelector(".thinking-text");
  const indicatorEl = thinkingEl.querySelector(".thinking-indicator");
  const onStatus = (statusMsg, level = "info") => {
    if (thinkingTextEl) {
      thinkingTextEl.textContent = statusMsg;
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
    // "warning" means the turn is still running but the provider is failing (retry or
    // failover), so the wait gets a visible reason instead of looking like a hang.
    if (indicatorEl) {
      indicatorEl.classList.toggle("degraded", level === "warning");
    }
  };

  try {
    const payload = {
      message: text,
      active_file: state.currentFile || null,
      active_file_summary: state.currentFileAiSummary || null,
    };

    const data = await postChatMessage(payload, state.sessionId, onStatus);

    thinkingEl.remove();

    state.sessionId = data.session_id;
    addChatMessage("assistant", data.reply);

    // Refresh the file tree immediately after the agent responds
    await loadFileTree();

    // If mutations happened: expand the folder, open the file and show a toast
    if (data.mutations && data.mutations.length > 0) {
      for (const m of data.mutations) {
        if (m.path && (m.tool === "create_file" || m.tool === "edit_file")) {
          const parts = m.path.split("/");
          if (parts.length > 1) {
            state.expandedFolders.add(parts.slice(0, -1).join("/"));
          }
          renderTree(explorerSearchInput ? explorerSearchInput.value : "");
          await loadFileContent(m.path);
          showToast(`Vault: ${m.path} updated`, "success");
        } else if (m.tool === "move_file") {
          if (m.path) {
            const parts = m.path.split("/");
            if (parts.length > 1) {
              state.expandedFolders.add(parts.slice(0, -1).join("/"));
            }
            renderTree(explorerSearchInput ? explorerSearchInput.value : "");
            await loadFileContent(m.path);
          }
          showToast(`Vault: ${m.path} moved`, "success");
        } else if (m.tool === "delete_file") {
          if (state.currentFile === m.path) {
            state.currentFile = null;
            emptyStateEl.style.display = "flex";
            fileContainerEl.style.display = "none";
          }
          showToast(`Vault: ${m.path} deleted`, "info");
        } else if (m.tool === "create_directory") {
          if (m.path) {
            state.expandedFolders.add(m.path);
            renderTree(explorerSearchInput ? explorerSearchInput.value : "");
          }
          showToast(`Folder created: ${m.path}`, "success");
        }
      }
    }

  } catch (err) {
    thinkingEl.remove();
    if (err.status === 404) {
      addChatMessage("error", "This session has expired. Please start a new chat.");
      state.sessionId = null;
      return;
    }
    addChatMessage("error", err.detail || (err.status ? err.message : `Verbindungsfehler: ${err.message}`));
  } finally {
    state.isSending = false;
    sendBtnEl.disabled = false;
    messageInputEl.focus();
  }
}

if (chatFormEl) {
  chatFormEl.addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.isSending) return;
    const text = messageInputEl.value.trim();
    if (!text) return;

    addChatMessage("user", text);
    messageInputEl.value = "";
    autoResizeTextarea();
    sendChatMessage(text);
  });
}

if (messageInputEl) {
  messageInputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatFormEl.requestSubmit();
    }
  });
}

if (newChatBtn) {
  newChatBtn.addEventListener("click", async () => {
    if (state.sessionId) {
      deleteSession(state.sessionId);
    }
    state.sessionId = null;
    messagesEl.innerHTML = "";
    addChatMessage("system", "Neuer Chat gestartet.");
    addChatMessage("assistant", "Wie kann ich dir bei deinem Vault helfen?");
    messageInputEl.focus();
  });
}
