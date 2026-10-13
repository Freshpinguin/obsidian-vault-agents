import { state } from "./state.js";
import { fetchFileContent } from "./api.js";
import { renderMarkdown } from "./markdown.js";
import { checkEditorDirty } from "./editor.js";
import { ensureFolderVisibleInTree } from "./tree.js";
import {
  emptyStateEl,
  fileContainerEl,
  viewerControlsEl,
  bcFilenameEl,
  docTitleTextEl,
  docDatesEl,
  docTagsEl,
  docAiBoxEl,
  docAiSummaryEl,
  docWikilinksEl,
  docWikilinksListEl,
  docBodyRenderedEl,
  docBodyRawEl,
  docBodyEditorEl,
  activeFilePill,
  activeFilePillText,
  chatFileContextBanner,
  chatContextBannerText,
} from "./dom.js";

// ==========================================
// 3. Dateiinhalt laden & anzeigen
// ==========================================
export async function loadFileContent(filePath) {
  try {
    // Markiere im Baum
    document.querySelectorAll(".node-row.active").forEach(el => el.classList.remove("active"));
    const activeEl = document.querySelector(`.node-row[data-path="${CSS.escape(filePath)}"]`);
    if (activeEl) activeEl.classList.add("active");

    const data = await fetchFileContent(filePath);

    state.currentFile = data.path;
    state.currentFileRawContent = data.raw_content;
    state.currentFileAiSummary = data.ai_summary || "";

    // Chat-Fokus und Kontext-Banner aktualisieren
    if (chatFileContextBanner && chatContextBannerText) {
      chatFileContextBanner.classList.add("active");
      chatContextBannerText.textContent = `Aktive Notiz: ${data.name || data.path}`;
    }
    if (activeFilePill && activeFilePillText) {
      activeFilePill.classList.add("has-file");
      activeFilePill.title = `Aktiver Fokus: ${data.path}\nai_map: ${data.ai_summary || "keine Zusammenfassung"}`;
      activeFilePillText.textContent = data.name || data.path.split("/").pop();
    }

    // Header & Breadcrumbs aktualisieren
    emptyStateEl.style.display = "none";
    fileContainerEl.style.display = "block";
    viewerControlsEl.style.display = "flex";

    const segments = data.path.split("/");
    bcFilenameEl.textContent = segments.join(" / ");
    docTitleTextEl.textContent = data.name;
    docDatesEl.textContent = `Zuletzt geändert: ${data.last_modified || "unbekannt"}`;

    // Tags
    docTagsEl.innerHTML = "";
    if (data.tags && data.tags.length > 0) {
      data.tags.forEach(tag => {
        const pill = document.createElement("span");
        pill.className = "tag-pill";
        pill.textContent = `#${tag}`;
        docTagsEl.appendChild(pill);
      });
    }

    // KI-Zusammenfassung Box
    if (data.ai_summary) {
      docAiSummaryEl.textContent = data.ai_summary;
    } else {
      docAiSummaryEl.innerHTML = `<span style="color: var(--text-muted); font-style: italic;">Noch keine Zusammenfassung hinterlegt. Klicke auf das Aktualisieren-Symbol (↻), um eine KI-Zusammenfassung zu generieren.</span>`;
    }
    docAiBoxEl.style.display = "flex";

    // Verknüpfte Notizen
    docWikilinksListEl.innerHTML = "";
    if (data.linked_files && data.linked_files.length > 0) {
      data.linked_files.forEach(link => {
        const chip = document.createElement("a");
        chip.className = "wikilink-chip";
        chip.textContent = `[[${link}]]`;
        chip.href = "javascript:void(0)";
        chip.addEventListener("click", () => loadFileContent(link));
        docWikilinksListEl.appendChild(chip);
      });
      docWikilinksEl.style.display = "flex";
    } else {
      docWikilinksEl.style.display = "none";
    }

    // Inhalt rendern & im Editor bereitstellen
    docBodyRenderedEl.innerHTML = renderMarkdown(data.body || data.raw_content);
    docBodyRawEl.textContent = data.raw_content;
    if (docBodyEditorEl) {
      docBodyEditorEl.value = data.raw_content;
    }
    checkEditorDirty();

    // Klickbare Wikilinks im gerenderten Text verdrahten
    docBodyRenderedEl.querySelectorAll(".wikilink").forEach(linkEl => {
      linkEl.addEventListener("click", () => {
        const target = linkEl.getAttribute("data-wikilink");
        if (target) loadFileContent(target);
      });
    });

    // Update Chat-Kontext-Pill
    activeFilePill.classList.add("has-file");
    activeFilePillText.textContent = data.name;
    activeFilePill.title = `Aktiver Dokumenten-Fokus: ${data.path}`;

    // Stelle sicher, dass die übergeordneten Ordner im Baum ausgeklappt sind
    ensureFolderVisibleInTree(filePath);

  } catch (err) {
    alert(`Fehler beim Öffnen von ${filePath}: ${err.message}`);
  }
}
