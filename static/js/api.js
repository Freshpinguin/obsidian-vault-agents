// ==========================================
// API Client
// ==========================================

export async function fetchFileTree() {
  const res = await fetch("/files");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function fetchFileContent(filePath) {
  const res = await fetch(`/files/content?path=${encodeURIComponent(filePath)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function saveFileContent(path, content) {
  const res = await fetch("/files/content", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `HTTP ${res.status}`);
  }
  return await res.json();
}

export async function deleteFile(path) {
  const res = await fetch(`/files/content?path=${encodeURIComponent(path)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `HTTP ${res.status}`);
  }
  return await res.json();
}

export async function requestFileSummary(path) {
  const res = await fetch("/files/summary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => ({}));
    throw new Error(errJson.detail || `HTTP ${res.status}`);
  }
  return await res.json();
}

export async function buildMissingSummaries() {
  const res = await fetch("/files/build-missing-summaries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return await res.json();
}

export async function postChatMessage(payload, sessionId, onStatus) {
  const url = sessionId ? `/sessions/${sessionId}/messages` : "/sessions";
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "text/event-stream, application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => ({}));
    const err = new Error(errJson.detail || `Error (${res.status}).`);
    err.status = res.status;
    err.detail = errJson.detail;
    throw err;
  }

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("text/event-stream") && res.body) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalData = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split("\n\n");
      buffer = parts.pop(); // incomplete remainder

      for (const block of parts) {
        for (const line of block.split("\n")) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === "status" && typeof onStatus === "function") {
                onStatus(event.message);
              } else if (event.type === "done") {
                finalData = event;
              } else if (event.type === "error") {
                const err = new Error(event.detail || "Error in the chat stream");
                err.detail = event.detail;
                throw err;
              }
            } catch (jsonErr) {
              if (jsonErr.detail) throw jsonErr;
              console.warn("Could not parse SSE event:", line, jsonErr);
            }
          }
        }
      }
    }

    if (finalData) {
      return finalData;
    }
    throw new Error("Stream beendet ohne finale Antwort.");
  }

  return await res.json();
}

export async function deleteSession(sessionId) {
  return fetch(`/sessions/${sessionId}`, { method: "DELETE" }).catch(() => {});
}

export async function moveNode(path, newPath) {
  const res = await fetch("/files/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, new_path: newPath }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `HTTP ${res.status}`);
  }
  return await res.json();
}

export async function createNote(path, content = "") {
  let notePath = (path || "").trim();
  if (notePath.toLowerCase().endsWith(".md")) {
    notePath = notePath.slice(0, -3) + ".md";
  } else {
    notePath += ".md";
  }

  const res = await fetch("/files/create-file", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: notePath, content }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `HTTP ${res.status}`);
  }
  return await res.json();
}
