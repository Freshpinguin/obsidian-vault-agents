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
// Request an AI summary (single file)
// ==========================================
export async function requestSummary() {
  if (!state.currentFile || state.isRequestingSummary) return;
  state.isRequestingSummary = true;

  if (btnRefreshSummaryCallout) {
    btnRefreshSummaryCallout.disabled = true;
    btnRefreshSummaryCallout.classList.add("spinning");
  }

  docAiBoxEl.style.display = "flex";
  docAiSummaryEl.innerHTML = `<span style="color: var(--accent-light);">✨ The summarizer agent is analyzing '${escapeHtml(state.currentFile)}' and generating a summary…</span>`;

  try {
    const data = await requestFileSummary(state.currentFile);

    docAiSummaryEl.textContent = data.ai_summary || "Summary created successfully.";
    state.currentFileAiSummary = data.ai_summary || "";
    if (activeFilePill) {
      activeFilePill.title = `Aktiver Fokus: ${state.currentFile}\nai_map: ${state.currentFileAiSummary}`;
    }

    if (data.file) {
      state.currentFileRawContent = data.file.raw_content;
      docDatesEl.textContent = `Last modified: ${data.file.last_modified || "just now"}`;
      if (state.viewMode === "raw") {
        docBodyRawEl.textContent = data.file.raw_content;
      }
    }

    // Refresh the file tree in the background (for hover summaries in the explorer)
    loadFileTree();

    showToast("✨ AI summary generated successfully.");

  } catch (err) {
    docAiSummaryEl.innerHTML = `<span style="color: var(--red);">Error: ${escapeHtml(err.message)}</span>`;
    showToast(`Error: ${err.message}`, "error");
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
// Create missing summaries (options menu)
// ==========================================
if (btnBuildMissingSummaries) {
  btnBuildMissingSummaries.addEventListener("click", async () => {
    btnBuildMissingSummaries.disabled = true;
    const origText = btnBuildMissingText ? btnBuildMissingText.textContent : "Fehlende Zusammenfassungen erstellen";
    if (btnBuildMissingText) btnBuildMissingText.textContent = "Scanning & summarizing the vault…";
    showToast("🚀 Scan started: creating the missing summaries…", "info");

    try {
      const data = await buildMissingSummaries();
      showToast(`✨ ${data.message}`, "success");
      await loadFileTree();
      if (state.currentFile) {
        await loadFileContent(state.currentFile);
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
    } finally {
      btnBuildMissingSummaries.disabled = false;
      if (btnBuildMissingText) btnBuildMissingText.textContent = origText;
    }
  });
}
