import { state } from "./state.js";
import { requestFileSummary, buildMissingSummaries } from "./api.js";
import { escapeHtml } from "./markdown.js";
import { showToast } from "./toast.js";
import { loadFileTree } from "./tree.js";
import { loadFileContent } from "./viewer.js";
import {
  btnRefreshSummaryCallout,
  docAiBoxEl,
  docAiSummaryEl,
  activeFilePill,
  docDatesEl,
  docBodyRawEl,
  btnBuildMissingSummaries,
  btnBuildMissingText,
} from "./dom.js";

// ==========================================
// KI-Zusammenfassung anfordern (einzelne Datei)
// ==========================================
export async function requestSummary() {
  if (!state.currentFile || state.isRequestingSummary) return;
  state.isRequestingSummary = true;

  if (btnRefreshSummaryCallout) {
    btnRefreshSummaryCallout.disabled = true;
    btnRefreshSummaryCallout.classList.add("spinning");
  }

  docAiBoxEl.style.display = "flex";
  docAiSummaryEl.innerHTML = `<span style="color: var(--accent-light);">✨ Der Summarizer-Agent analysiert '${escapeHtml(state.currentFile)}' und generiert eine Zusammenfassung…</span>`;

  try {
    const data = await requestFileSummary(state.currentFile);

    docAiSummaryEl.textContent = data.ai_summary || "Zusammenfassung erfolgreich erstellt.";
    state.currentFileAiSummary = data.ai_summary || "";
    if (activeFilePill) {
      activeFilePill.title = `Aktiver Fokus: ${state.currentFile}\nai_map: ${state.currentFileAiSummary}`;
    }

    if (data.file) {
      state.currentFileRawContent = data.file.raw_content;
      docDatesEl.textContent = `Zuletzt geändert: ${data.file.last_modified || "gerade eben"}`;
      if (state.viewMode === "raw") {
        docBodyRawEl.textContent = data.file.raw_content;
      }
    }

    // Dateibaum im Hintergrund aktualisieren (für Hover-Zusammenfassungen im Explorer)
    loadFileTree();

    showToast("✨ KI-Zusammenfassung erfolgreich generiert!");

  } catch (err) {
    docAiSummaryEl.innerHTML = `<span style="color: var(--red);">Fehler: ${escapeHtml(err.message)}</span>`;
    showToast(`Fehler: ${err.message}`, "error");
  } finally {
    state.isRequestingSummary = false;
    if (btnRefreshSummaryCallout) {
      btnRefreshSummaryCallout.disabled = false;
      btnRefreshSummaryCallout.classList.remove("spinning");
    }
  }
}

if (btnRefreshSummaryCallout) {
  btnRefreshSummaryCallout.addEventListener("click", requestSummary);
}

// ==========================================
// Fehlende Zusammenfassungen erstellen (Optionen-Menü)
// ==========================================
if (btnBuildMissingSummaries) {
  btnBuildMissingSummaries.addEventListener("click", async () => {
    btnBuildMissingSummaries.disabled = true;
    const origText = btnBuildMissingText ? btnBuildMissingText.textContent : "Fehlende Zusammenfassungen erstellen";
    if (btnBuildMissingText) btnBuildMissingText.textContent = "Vault wird gescannt & zusammengefasst…";
    showToast("🚀 Scan gestartet: Fehlende Zusammenfassungen werden erstellt…", "info");

    try {
      const data = await buildMissingSummaries();
      showToast(`✨ ${data.message}`, "success");
      await loadFileTree();
      if (state.currentFile) {
        await loadFileContent(state.currentFile);
      }
    } catch (err) {
      showToast(`Fehler: ${err.message}`, "error");
    } finally {
      btnBuildMissingSummaries.disabled = false;
      if (btnBuildMissingText) btnBuildMissingText.textContent = origText;
    }
  });
}
