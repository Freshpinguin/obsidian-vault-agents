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

export async function postChatMessage(payload, sessionId) {
  const url = sessionId ? `/sessions/${sessionId}/messages` : "/sessions";
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => ({}));
    const err = new Error(errJson.detail || `Fehler (${res.status}).`);
    err.status = res.status;
    err.detail = errJson.detail;
    throw err;
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
  const res = await fetch("/files/create-file", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || `HTTP ${res.status}`);
  }
  return await res.json();
}
