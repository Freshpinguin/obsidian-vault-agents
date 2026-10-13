import {
  explorerPane,
  chatPane,
  btnToggleExplorer,
  btnToggleChat,
} from "./dom.js";

// ==========================================
// 6. Pane-Umschalter (Explorer & Chat Toggle)
// ==========================================
if (btnToggleExplorer) {
  btnToggleExplorer.addEventListener("click", () => {
    explorerPane.classList.toggle("collapsed");
  });
}

if (btnToggleChat) {
  btnToggleChat.addEventListener("click", () => {
    chatPane.classList.toggle("collapsed");
  });
}

// ==========================================
// 8. Resizable Split Panes (Mouse Dragging)
// ==========================================
export function setupResizer(resizerEl, leftPane, isReverse = false) {
  if (!resizerEl || !leftPane) return;
  let isDragging = false;
  let startX = 0;
  let startWidth = 0;

  resizerEl.addEventListener("mousedown", (e) => {
    isDragging = true;
    startX = e.clientX;
    startWidth = leftPane.getBoundingClientRect().width;
    resizerEl.classList.add("dragging");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  });

  window.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const delta = e.clientX - startX;
    const newWidth = isReverse ? (startWidth - delta) : (startWidth + delta);
    if (newWidth > 200 && newWidth < 800) {
      leftPane.style.width = `${newWidth}px`;
    }
  });

  window.addEventListener("mouseup", () => {
    if (isDragging) {
      isDragging = false;
      resizerEl.classList.remove("dragging");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
  });
}

setupResizer(document.getElementById("resizer-1"), explorerPane);
setupResizer(document.getElementById("resizer-2"), chatPane, true);
