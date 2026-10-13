import { closeDeleteModal } from "./editor.js";
import { showToast } from "./toast.js";
import { initFileWatcherEvents, stopFileWatcherEvents } from "./live.js";

// ==========================================
// 10. Optionen & Einstellungen
// ==========================================
export const SETTINGS_KEY = "obsidian_agents_ui_settings";
export const defaultSettings = {
  showMetadataBox: true,
  showAiSummary: true,
  showWikilinks: true,
  liveSyncEnabled: true,
  fontSize: "normal",
};

export let currentSettings = { ...defaultSettings };

export function loadSettings() {
  try {
    const saved = localStorage.getItem(SETTINGS_KEY);
    if (saved) {
      currentSettings = { ...defaultSettings, ...JSON.parse(saved) };
    }
  } catch (_) {}
  applySettings();
}

export function saveSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(currentSettings));
  } catch (_) {}
  applySettings();
}

export function applySettings() {
  // 1. The whole metadata block
  if (currentSettings.showMetadataBox) {
    document.body.classList.remove("hide-file-metadata");
  } else {
    document.body.classList.add("hide-file-metadata");
  }

  // 2. AI summary box
  if (currentSettings.showAiSummary) {
    document.body.classList.remove("hide-ai-summary");
  } else {
    document.body.classList.add("hide-ai-summary");
  }

  // 3. Linked-notes box
  if (currentSettings.showWikilinks) {
    document.body.classList.remove("hide-wikilinks");
  } else {
    document.body.classList.add("hide-wikilinks");
  }

  // 4. Text size
  document.body.classList.remove("font-compact", "font-large");
  if (currentSettings.fontSize === "compact") {
    document.body.classList.add("font-compact");
  } else if (currentSettings.fontSize === "large") {
    document.body.classList.add("font-large");
  }

  // Keep the inputs in the modal in sync
  const cbMeta = document.getElementById("setting-show-metadata");
  if (cbMeta) cbMeta.checked = currentSettings.showMetadataBox;

  const cbAi = document.getElementById("setting-show-ai-summary");
  if (cbAi) cbAi.checked = currentSettings.showAiSummary;

  const cbWiki = document.getElementById("setting-show-wikilinks");
  if (cbWiki) cbWiki.checked = currentSettings.showWikilinks;

  const cbSync = document.getElementById("setting-live-sync");
  if (cbSync) cbSync.checked = currentSettings.liveSyncEnabled;

  document.querySelectorAll(".font-size-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.size === currentSettings.fontSize);
  });
}

export function openSettingsModal() {
  applySettings();
  const modal = document.getElementById("settings-modal");
  if (modal) modal.classList.add("open");
}

export function closeSettingsModal() {
  const modal = document.getElementById("settings-modal");
  if (modal) modal.classList.remove("open");
}

// Event listeners for the options
const btnOpenSettings = document.getElementById("btn-open-settings");
const btnExplorerSettings = document.getElementById("btn-explorer-settings");
const btnFloatingSettings = document.getElementById("btn-floating-settings");
const btnCloseSettings = document.getElementById("btn-close-settings");
const btnSaveSettingsClose = document.getElementById("btn-save-settings-close");

if (btnOpenSettings) btnOpenSettings.addEventListener("click", openSettingsModal);
if (btnExplorerSettings) btnExplorerSettings.addEventListener("click", openSettingsModal);
if (btnFloatingSettings) btnFloatingSettings.addEventListener("click", openSettingsModal);
if (btnCloseSettings) btnCloseSettings.addEventListener("click", closeSettingsModal);
if (btnSaveSettingsClose) btnSaveSettingsClose.addEventListener("click", closeSettingsModal);

// Global click delegation for close buttons and the backdrop
document.addEventListener("click", (e) => {
  if (e.target.closest("#btn-close-settings") || e.target.closest("#btn-save-settings-close")) {
    closeSettingsModal();
  } else if (e.target === document.getElementById("settings-modal")) {
    closeSettingsModal();
  } else if (e.target.closest("#btn-close-delete-modal") || e.target.closest("#btn-cancel-delete")) {
    closeDeleteModal();
  } else if (e.target === document.getElementById("delete-modal")) {
    closeDeleteModal();
  }
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const modal = document.getElementById("settings-modal");
    if (modal && modal.classList.contains("open")) {
      closeSettingsModal();
    }
    const delModal = document.getElementById("delete-modal");
    if (delModal && delModal.classList.contains("open")) {
      closeDeleteModal();
    }
  }
});

const cbMeta = document.getElementById("setting-show-metadata");
if (cbMeta) {
  cbMeta.addEventListener("change", (e) => {
    currentSettings.showMetadataBox = e.target.checked;
    saveSettings();
    showToast(e.target.checked ? "Metadaten-Block eingeblendet" : "Metadaten-Block ausgeblendet", "info");
  });
}

const cbAi = document.getElementById("setting-show-ai-summary");
if (cbAi) {
  cbAi.addEventListener("change", (e) => {
    currentSettings.showAiSummary = e.target.checked;
    saveSettings();
  });
}

const cbWiki = document.getElementById("setting-show-wikilinks");
if (cbWiki) {
  cbWiki.addEventListener("change", (e) => {
    currentSettings.showWikilinks = e.target.checked;
    saveSettings();
  });
}

const cbSync = document.getElementById("setting-live-sync");
if (cbSync) {
  cbSync.addEventListener("change", (e) => {
    currentSettings.liveSyncEnabled = e.target.checked;
    saveSettings();
    if (e.target.checked) {
      initFileWatcherEvents();
    } else {
      stopFileWatcherEvents();
    }
  });
}

document.querySelectorAll(".font-size-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    currentSettings.fontSize = btn.dataset.size;
    saveSettings();
  });
});
