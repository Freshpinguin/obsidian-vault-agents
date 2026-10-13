import { loadSettings, currentSettings } from "./settings.js";
import { loadFileTree } from "./tree.js";
import { initFileWatcherEvents } from "./live.js";
import "./panes.js";
import "./editor.js";
import "./chat.js";
import "./summaries.js";

// ==========================================
// 11. Initialisierung
// ==========================================
loadSettings();
loadFileTree();
if (currentSettings.liveSyncEnabled) {
  initFileWatcherEvents();
}
