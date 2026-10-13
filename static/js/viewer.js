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
// 3. Load & display file content
// ==========================================
export async function loadFileContent(filePath) {
  try {
    // Highlight it in the tree
    document.querySelectorAll(".node-row.active").forEach(el => el.classList.remove("active"));
    const activeEl = document.querySelector(`.node-row[data-path="${CSS.escape(filePath)}"]`);
    if (activeEl) activeEl.classList.add("active");

    const data = await fetchFileContent(filePath);

    state.currentFile = data.path;
    state.currentFileRawContent = data.raw_content;
    state.currentFileAiSummary = data.ai_summary || "";

    // Update the chat focus and context banner
    if (chatFileContextBanner && chatContextBannerText) {
      chatFileContextBanner.classList.add("active");
      chatContextBannerText.textContent = `Active note: ${data.name || data.path}`;
    }
    if (activeFilePill && activeFilePillText) {
      activeFilePill.classList.add("has-file");
      activeFilePill.title = `Active focus: ${data.path}\nai_map: ${data.ai_summary || "no summary"}`;
      activeFilePillText.textContent = data.name || data.path.split("/").pop();
    }

    // Update the header & breadcrumbs
    emptyStateEl.style.display = "none";
    fileContainerEl.style.display = "block";
    viewerControlsEl.style.display = "flex";

    const segments = data.path.split("/");
    bcFilenameEl.textContent = segments.join(" / ");
    docTitleTextEl.textContent = data.name;
    docDatesEl.textContent = `Last modified: ${data.last_modified || "unknown"}`;

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

    // AI summary box
    if (data.ai_summary) {
      docAiSummaryEl.textContent = data.ai_summary;
    } else {
      docAiSummaryEl.innerHTML = `<span style="color: var(--text-muted); font-style: italic;">No summary stored yet. Click the refresh icon (↻) to generate an AI summary.</span>`;
    }
    docAiBoxEl.style.display = "flex";

    // Linked notes
    docWikilinksListEl.innerHTML = "";
    if (data.linked_files && data.linked_files.length > 0) {
      data.linked_files.forEach(link => {
        const chip = document.createElement("a");
        chip.className = "wikilink-chip";
        // Display without the .md, like the inline wikilinks in the body; the click
        // still uses the full resolved path.
        chip.textContent = `[[${link.replace(/\.md$/, "")}]]`;
        chip.href = "javascript:void(0)";
        chip.addEventListener("click", () => loadFileContent(link));
        docWikilinksListEl.appendChild(chip);
      });
      docWikilinksEl.style.display = "flex";
    } else {
      docWikilinksEl.style.display = "none";
    }

    // Render the content & load it into the editor
    docBodyRenderedEl.innerHTML = renderMarkdown(data.body || data.raw_content);
    docBodyRawEl.textContent = data.raw_content;
    if (docBodyEditorEl) {
      docBodyEditorEl.value = data.raw_content;
    }
    checkEditorDirty();

    // Wire up clickable wikilinks in the rendered text
    docBodyRenderedEl.querySelectorAll(".wikilink").forEach(linkEl => {
      linkEl.addEventListener("click", (e) => {
        e.preventDefault();
        const target = linkEl.getAttribute("data-wikilink");
        if (target) loadFileContent(target);
      });
    });

    // Update the chat context pill
    activeFilePill.classList.add("has-file");
    activeFilePillText.textContent = data.name;
    activeFilePill.title = `Aktiver Dokumenten-Fokus: ${data.path}`;

    // Make sure the parent folders in the tree are expanded
    ensureFolderVisibleInTree(filePath);

  } catch (err) {
    alert(`Error opening ${filePath}: ${err.message}`);
  }
}
