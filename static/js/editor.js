import { state } from "./state.js";
import { saveFileContent, deleteFile } from "./api.js";
import { renderMarkdown } from "./markdown.js";
import { showToast } from "./toast.js";
import { loadFileContent } from "./viewer.js";
import { loadFileTree } from "./tree.js";
import {
  btnModeRendered,
  btnModeRaw,
  btnSaveContent,
  btnSaveLabel,
  btnCopyContent,
  btnDeleteFile,
  docEditorContainerEl,
  docBodyEditorEl,
  docBodyRenderedEl,
  docBodyRawEl,
  editorStatusDotEl,
  editorStatusTextEl,
  docDatesEl,
  deleteModal,
  deleteFileNameEl,
  btnConfirmDelete,
  btnCancelDelete,
  btnCloseDeleteModal,
  fileContainerEl,
  viewerControlsEl,
  emptyStateEl,
  bcFilenameEl,
  activeFilePill,
  activeFilePillText,
  chatFileContextBanner,
} from "./dom.js";

// ==========================================
// 4. View mode toggle, editor & file operations (save & delete)
// ==========================================
export function checkEditorDirty() {
  if (!docBodyEditorEl) return;
  const isDirty = docBodyEditorEl.value !== state.currentFileRawContent;
  if (editorStatusDotEl) {
    editorStatusDotEl.classList.toggle("unsaved", isDirty);
  }
  if (editorStatusTextEl) {
    editorStatusTextEl.textContent = isDirty ? "Unsaved changes" : "Ready to edit";
  }
  if (btnSaveContent) {
    btnSaveContent.classList.toggle("unsaved", isDirty);
  }
  if (btnSaveLabel) {
    btnSaveLabel.textContent = isDirty ? "Save *" : "Save";
  }
}

if (btnModeRendered) {
  btnModeRendered.addEventListener("click", () => {
    state.viewMode = "rendered";
    btnModeRendered.classList.add("active");
    btnModeRaw.classList.remove("active");
    docBodyRenderedEl.style.display = "block";
    if (docEditorContainerEl) docEditorContainerEl.style.display = "none";
    docBodyRawEl.style.display = "none";

    // Immediately renders any changes written in the editor into the preview
    if (docBodyEditorEl) {
      docBodyRenderedEl.innerHTML = renderMarkdown(docBodyEditorEl.value);
      docBodyRenderedEl.querySelectorAll(".wikilink").forEach(linkEl => {
        linkEl.addEventListener("click", (e) => {
          e.preventDefault();
          const target = linkEl.getAttribute("data-wikilink");
          if (target) loadFileContent(target);
        });
      });
    }
  });
}

if (btnModeRaw) {
  btnModeRaw.addEventListener("click", () => {
    state.viewMode = "raw";
    btnModeRaw.classList.add("active");
    btnModeRendered.classList.remove("active");
    docBodyRenderedEl.style.display = "none";
    if (docEditorContainerEl) docEditorContainerEl.style.display = "flex";
    docBodyRawEl.style.display = "none";
    if (docBodyEditorEl) docBodyEditorEl.focus();
  });
}

// Editor Eingabe- & Tab-Events
if (docBodyEditorEl) {
  docBodyEditorEl.addEventListener("input", checkEditorDirty);
  docBodyEditorEl.addEventListener("keydown", (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const start = docBodyEditorEl.selectionStart;
      const end = docBodyEditorEl.selectionEnd;
      docBodyEditorEl.value = docBodyEditorEl.value.substring(0, start) + "  " + docBodyEditorEl.value.substring(end);
      docBodyEditorEl.selectionStart = docBodyEditorEl.selectionEnd = start + 2;
      checkEditorDirty();
    }
  });
}

// Save file
export async function saveCurrentFile() {
  if (!state.currentFile || state.isSavingFile || !docBodyEditorEl) return;
  state.isSavingFile = true;
  if (btnSaveLabel) btnSaveLabel.textContent = "Speichert...";
  btnSaveContent.disabled = true;

  try {
    const content = docBodyEditorEl.value;
    const data = await saveFileContent(state.currentFile, content);
    state.currentFileRawContent = data.file ? data.file.raw_content : content;
    if (data.file) {
      docDatesEl.textContent = `Last modified: ${data.file.last_modified || "just now"}`;
      docBodyRenderedEl.innerHTML = renderMarkdown(data.file.body || content);
      docBodyRenderedEl.querySelectorAll(".wikilink").forEach(linkEl => {
        linkEl.addEventListener("click", (e) => {
          e.preventDefault();
          const target = linkEl.getAttribute("data-wikilink");
          if (target) loadFileContent(target);
        });
      });
    }
    checkEditorDirty();
    showToast("Note saved successfully.", "success");
  } catch (err) {
    showToast(`Error while saving: ${err.message}`, "error");
  } finally {
    state.isSavingFile = false;
    btnSaveContent.disabled = false;
    checkEditorDirty();
  }
}

if (btnSaveContent) {
  btnSaveContent.addEventListener("click", saveCurrentFile);
}

// Keyboard shortcut Cmd+S / Ctrl+S to save
window.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && (e.key === "s" || e.key === "S")) {
    if (state.currentFile) {
      e.preventDefault();
      saveCurrentFile();
    }
  }
});

// Delete file (modal & confirmation)
export function openDeleteModal() {
  if (!state.currentFile) return;
  if (deleteFileNameEl) deleteFileNameEl.textContent = state.currentFile.split("/").pop();
  if (deleteModal) deleteModal.classList.add("open");
}

export function closeDeleteModal() {
  if (deleteModal) deleteModal.classList.remove("open");
}

if (btnDeleteFile) {
  btnDeleteFile.addEventListener("click", openDeleteModal);
}

if (btnCancelDelete) {
  btnCancelDelete.addEventListener("click", closeDeleteModal);
}

if (btnCloseDeleteModal) {
  btnCloseDeleteModal.addEventListener("click", closeDeleteModal);
}

if (btnConfirmDelete) {
  btnConfirmDelete.addEventListener("click", async () => {
    if (!state.currentFile || state.isDeletingFile) return;
    state.isDeletingFile = true;
    const btnConfirmText = document.getElementById("btn-confirm-delete-text");
    if (btnConfirmText) btnConfirmText.textContent = "Deleting...";
    btnConfirmDelete.disabled = true;

    try {
      const targetPath = state.currentFile;
      await deleteFile(targetPath);
      closeDeleteModal();
      showToast(`Note '${targetPath.split("/").pop()}' was deleted.`, "success");

      state.currentFile = null;
      state.currentFileRawContent = "";
      state.currentFileAiSummary = "";
      fileContainerEl.style.display = "none";
      viewerControlsEl.style.display = "none";
      emptyStateEl.style.display = "flex";
      bcFilenameEl.textContent = "No file open";

      if (activeFilePill && activeFilePillText) {
        activeFilePill.classList.remove("has-file");
        activeFilePillText.textContent = "Kein Fokus";
        activeFilePill.title = "No file selected";
      }
      if (chatFileContextBanner) {
        chatFileContextBanner.classList.remove("active");
      }

      await loadFileTree();
    } catch (err) {
      showToast(`Error while deleting: ${err.message}`, "error");
    } finally {
      state.isDeletingFile = false;
      btnConfirmDelete.disabled = false;
      if (btnConfirmText) btnConfirmText.textContent = "Delete";
    }
  });
}

if (btnCopyContent) {
  btnCopyContent.addEventListener("click", () => {
    const textToCopy = docBodyEditorEl ? docBodyEditorEl.value : state.currentFileRawContent;
    if (!textToCopy) return;
    navigator.clipboard.writeText(textToCopy).then(() => {
      btnCopyContent.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`;
      setTimeout(() => {
        btnCopyContent.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
      }, 1500);
    });
  });
}
