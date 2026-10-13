import { state } from "./state.js";
import { fetchFileTree, moveNode } from "./api.js";
import { showToast } from "./toast.js";
import { escapeHtml } from "./markdown.js";
import {
  fileTreeEl,
  explorerSearchInput,
  quickCardsEl,
  btnExpandAll,
  btnCollapseAll,
  btnRefreshTree,
} from "./dom.js";
import { loadFileContent } from "./viewer.js";

// ==========================================
// 2. Dateibaum laden & darstellen
// ==========================================
export async function loadFileTree() {
  try {
    const data = await fetchFileTree();
    state.vaultTreeData = data;

    if (data.root_path) {
      const rootEl = document.getElementById("vault-root-path");
      if (rootEl) {
        const parts = data.root_path.split("/");
        rootEl.textContent = parts.slice(-2).join("/");
      }
    }

    // Bei erstem Laden alle Hauptordner expandieren
    if (state.expandedFolders.size === 0 && data.items) {
      data.items.forEach(item => {
        if (item.type === "directory") state.expandedFolders.add(item.path);
      });
    }

    renderTree(explorerSearchInput ? explorerSearchInput.value : "");
    renderQuickCards(data);
  } catch (err) {
    fileTreeEl.innerHTML = `
      <div style="padding: 1rem; color: var(--red); font-size: 0.8rem;">
        Fehler beim Laden des Vaults: ${escapeHtml(err.message)}
      </div>
    `;
  }
}

export function renderTree(filterText = "") {
  if (!state.vaultTreeData || !state.vaultTreeData.items) return;
  const filter = filterText.trim().toLowerCase();
  fileTreeEl.innerHTML = "";

  const domList = buildTreeDOM(state.vaultTreeData.items, filter);
  if (domList.length === 0) {
    fileTreeEl.innerHTML = `<div style="padding: 0.75rem; color: var(--text-muted); font-size: 0.78rem;">Keine passenden Dateien gefunden.</div>`;
  } else {
    domList.forEach(node => fileTreeEl.appendChild(node));
  }
}

export function buildTreeDOM(items, filter = "") {
  const nodes = [];

  for (const item of items) {
    const isDir = item.type === "directory";
    const matchesSelf = item.name.toLowerCase().includes(filter);

    if (isDir) {
      const childNodes = buildTreeDOM(item.children || [], filter);
      // Ordner anzeigen wenn Name passt oder ein Kind passt
      if (!filter || matchesSelf || childNodes.length > 0) {
        const folderNode = document.createElement("div");
        const isExpanded = filter ? true : state.expandedFolders.has(item.path);
        folderNode.className = `tree-node folder-node ${isExpanded ? "expanded" : ""}`;

        const row = document.createElement("div");
        row.className = "node-row";
        row.title = item.ai_summary || item.path;

        row.innerHTML = `
          <span class="node-chevron">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
          </span>
          <span class="node-icon folder">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          </span>
          <span class="node-label">${escapeHtml(item.name)}</span>
          <span class="node-count">${(item.children || []).length}</span>
        `;

        // Drag & Drop auf Ordner-Element (gesamter Teilbaum)
        folderNode.addEventListener("dragover", (e) => {
          e.preventDefault();
          e.stopPropagation();
          e.dataTransfer.dropEffect = "move";
          row.classList.add("drop-target");
        });

        folderNode.addEventListener("dragleave", (e) => {
          if (!folderNode.contains(e.relatedTarget)) {
            row.classList.remove("drop-target");
          }
        });

        folderNode.addEventListener("drop", async (e) => {
          e.preventDefault();
          e.stopPropagation();
          row.classList.remove("drop-target");

          const sourcePath = e.dataTransfer.getData("text/plain");
          if (!sourcePath) return;

          const base = sourcePath.split("/").pop();
          const newPath = item.path + "/" + base;

          if (newPath === sourcePath) return;

          try {
            const res = await moveNode(sourcePath, newPath);
            showToast(res.message);
            state.expandedFolders.add(item.path);
            await loadFileTree();
          } catch (err) {
            showToast(err.message, "error");
          }
        });

        row.addEventListener("click", (e) => {
          e.stopPropagation();
          if (state.expandedFolders.has(item.path)) {
            state.expandedFolders.delete(item.path);
            folderNode.classList.remove("expanded");
          } else {
            state.expandedFolders.add(item.path);
            folderNode.classList.add("expanded");
          }
        });

        const childrenContainer = document.createElement("div");
        childrenContainer.className = "tree-children";
        childNodes.forEach(c => childrenContainer.appendChild(c));

        folderNode.appendChild(row);
        folderNode.appendChild(childrenContainer);
        nodes.push(folderNode);
      }
    } else {
      // Datei
      if (!filter || matchesSelf) {
        const fileNode = document.createElement("div");
        fileNode.className = "tree-node file-node";

        const row = document.createElement("div");
        row.className = `node-row ${state.currentFile === item.path ? "active" : ""}`;
        row.dataset.path = item.path;
        row.title = item.ai_summary || item.name;

        // Drag & Drop auf Datei-Zeile
        row.draggable = true;
        row.addEventListener("dragstart", (e) => {
          e.dataTransfer.setData("text/plain", item.path);
          e.dataTransfer.effectAllowed = "move";
          row.classList.add("dragging");
        });
        row.addEventListener("dragend", () => {
          row.classList.remove("dragging");
        });

        row.innerHTML = `
          <span style="width: 14px;"></span>
          <span class="node-icon file">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          </span>
          <span class="node-label">${escapeHtml(item.name)}</span>
        `;

        row.addEventListener("click", () => {
          loadFileContent(item.path);
        });

        fileNode.appendChild(row);
        nodes.push(fileNode);
      }
    }
  }

  return nodes;
}

export function renderQuickCards(treeData) {
  if (!quickCardsEl) return;
  quickCardsEl.innerHTML = "";

  // Finde bis zu 4 Notizen für das Schnellstart-Dashboard
  const sampleFiles = [];
  function collect(items) {
    for (const it of items) {
      if (it.type === "file") sampleFiles.push(it);
      else if (it.children) collect(it.children);
    }
  }
  collect(treeData.items || []);

  sampleFiles.slice(0, 4).forEach(file => {
    const card = document.createElement("div");
    card.className = "quick-card";
    card.innerHTML = `
      <div class="quick-card-title">📝 ${escapeHtml(file.name)}</div>
      <div class="quick-card-desc">${escapeHtml(file.ai_summary || "Klicke zum Öffnen")}</div>
    `;
    card.addEventListener("click", () => loadFileContent(file.path));
    quickCardsEl.appendChild(card);
  });
}

export function ensureFolderVisibleInTree(filePath) {
  const parts = filePath.split("/");
  let cur = "";
  for (let i = 0; i < parts.length - 1; i++) {
    cur = cur ? `${cur}/${parts[i]}` : parts[i];
    state.expandedFolders.add(cur);
  }
  renderTree(explorerSearchInput ? explorerSearchInput.value : "");
}

// ==========================================
// 5. Explorer Suchfilter & Aktionen
// ==========================================
if (explorerSearchInput) {
  explorerSearchInput.addEventListener("input", (e) => {
    renderTree(e.target.value);
  });
}

if (btnExpandAll) {
  btnExpandAll.addEventListener("click", () => {
    function expandRecursive(items) {
      for (const it of items) {
        if (it.type === "directory") {
          state.expandedFolders.add(it.path);
          if (it.children) expandRecursive(it.children);
        }
      }
    }
    if (state.vaultTreeData && state.vaultTreeData.items) expandRecursive(state.vaultTreeData.items);
    renderTree(explorerSearchInput ? explorerSearchInput.value : "");
  });
}

if (btnCollapseAll) {
  btnCollapseAll.addEventListener("click", () => {
    state.expandedFolders.clear();
    renderTree(explorerSearchInput ? explorerSearchInput.value : "");
  });
}

if (btnRefreshTree) {
  btnRefreshTree.addEventListener("click", () => {
    loadFileTree();
  });
}

// Vault-Root als Drop-Ziel für fileTreeEl
if (fileTreeEl) {
  fileTreeEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  });

  fileTreeEl.addEventListener("drop", async (e) => {
    e.preventDefault();
    const sourcePath = e.dataTransfer.getData("text/plain");
    if (!sourcePath) return;

    const base = sourcePath.split("/").pop();
    const newPath = base;

    if (newPath === sourcePath) return;

    try {
      const res = await moveNode(sourcePath, newPath);
      showToast(res.message);
      await loadFileTree();
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}
