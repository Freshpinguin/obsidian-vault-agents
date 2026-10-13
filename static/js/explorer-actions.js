import { state } from "./state.js";
import { createNote } from "./api.js";
import { showToast } from "./toast.js";
import { loadFileTree } from "./tree.js";
import { loadFileContent } from "./viewer.js";
import {
  btnNewFile,
  createModal,
  createModalTitle,
  createNameInput,
  btnConfirmCreate,
  btnCancelCreate,
  btnCloseCreateModal,
} from "./dom.js";

// Ordner-Erstellung ist im Frontend vorlaeufig entfernt; Agenten legen Ordner
// weiterhin ueber vault_mutation.create_directory an.
export function openCreateModal() {
  if (createModalTitle) {
    createModalTitle.textContent = "Neue Notiz";
  }
  if (createNameInput) {
    createNameInput.value = "";
    createNameInput.placeholder = "Notizname (z. B. Meine Notiz)";
  }
  if (createModal) {
    createModal.classList.add("open");
  }
  if (createNameInput) {
    setTimeout(() => createNameInput.focus(), 50);
  }
}

export function closeCreateModal() {
  if (createModal) {
    createModal.classList.remove("open");
  }
}

async function handleConfirmCreate() {
  if (!createNameInput) return;
  const name = createNameInput.value.trim();
  if (!name) {
    showToast("Bitte einen Namen eingeben.", "error");
    return;
  }

  // Übergeordneter Ordner: Ordner der aktuell geöffneten Notiz oder Vault-Root
  let parent = "";
  if (state.currentFile && state.currentFile.includes("/")) {
    parent = state.currentFile.substring(0, state.currentFile.lastIndexOf("/"));
  }

  let cleanName = name.replace(/\\/g, "/").trim().replace(/^\/+/, "");
  if (!cleanName || cleanName === ".md") {
    showToast("Bitte einen gültigen Notiznamen eingeben.", "error");
    return;
  }

  // Notizen werden immer als .md Datei angelegt
  if (cleanName.toLowerCase().endsWith(".md")) {
    cleanName = cleanName.slice(0, -3) + ".md";
  } else {
    cleanName += ".md";
  }

  const path = parent ? `${parent}/${cleanName}` : cleanName;

  try {
    const res = await createNote(path);
    showToast(res.message);
    closeCreateModal();
    await loadFileTree();
    if (res.path) {
      await loadFileContent(res.path);
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}

if (btnNewFile) {
  btnNewFile.addEventListener("click", () => openCreateModal());
}

if (btnCancelCreate) {
  btnCancelCreate.addEventListener("click", closeCreateModal);
}

if (btnCloseCreateModal) {
  btnCloseCreateModal.addEventListener("click", closeCreateModal);
}

if (btnConfirmCreate) {
  btnConfirmCreate.addEventListener("click", handleConfirmCreate);
}

if (createNameInput) {
  createNameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleConfirmCreate();
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeCreateModal();
    }
  });
}
