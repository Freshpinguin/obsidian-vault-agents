import { state } from "./state.js";
import { loadFileTree } from "./tree.js";
import { loadFileContent } from "./viewer.js";

// ==========================================
// 9. Realtime Live-Refresh via SSE (/files/events)
// ==========================================
let refreshDebounceTimer = null;
export let fileEventSource = null;

export function scheduleFileTreeRefresh(delayMs = 300, modifiedPath = null) {
  if (refreshDebounceTimer) clearTimeout(refreshDebounceTimer);
  refreshDebounceTimer = setTimeout(async () => {
    await loadFileTree();
    // Falls die aktuell im Editor geöffnete Datei geändert wurde,
    // deren Inhalt und Zusammenfassung ebenfalls aktualisieren
    if (modifiedPath && state.currentFile && modifiedPath.endsWith(state.currentFile)) {
      await loadFileContent(state.currentFile);
    }
  }, delayMs);
}

export function stopFileWatcherEvents() {
  if (fileEventSource) {
    fileEventSource.close();
    fileEventSource = null;
  }
}

export function initFileWatcherEvents() {
  if (!window.EventSource) {
    console.warn("EventSource nicht unterstützt. Verwende Fallback-Polling.");
    setInterval(() => loadFileTree(), 5000);
    return;
  }

  try {
    if (fileEventSource) {
      fileEventSource.close();
    }
    fileEventSource = new EventSource("/files/events");

    fileEventSource.addEventListener("connected", () => {
      console.log("[Live-Sync] Echtzeit-Verbindung für Vault-Änderungen aktiv.");
    });

    const handleVaultChange = (e) => {
      try {
        const data = JSON.parse(e.data || "{}");
        const changedPath = data.path || data.dest_path || data.src_path;
        scheduleFileTreeRefresh(300, changedPath);
      } catch (_) {
        scheduleFileTreeRefresh(300);
      }
    };

    fileEventSource.addEventListener("created", handleVaultChange);
    fileEventSource.addEventListener("modified", handleVaultChange);
    fileEventSource.addEventListener("deleted", handleVaultChange);
    fileEventSource.addEventListener("moved", handleVaultChange);
    fileEventSource.addEventListener("dir_created", handleVaultChange);
    fileEventSource.addEventListener("dir_deleted", handleVaultChange);
    fileEventSource.addEventListener("dir_moved", handleVaultChange);
    fileEventSource.addEventListener("change", handleVaultChange);

    fileEventSource.onerror = () => {
      // EventSource unternimmt automatisch im Hintergrund Reconnects
    };
  } catch (err) {
    console.error("[Live-Sync] Fehler bei EventSource:", err);
    setInterval(() => loadFileTree(), 5000);
  }
}
