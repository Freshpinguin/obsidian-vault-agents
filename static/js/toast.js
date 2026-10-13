import { toastContainerEl } from "./dom.js";
import { escapeHtml } from "./markdown.js";

// ==========================================
// Toast Benachrichtigungen
// ==========================================
export function showToast(message, type = "success") {
  if (!toastContainerEl) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  const icon = type === "success" 
    ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
    : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
  toast.innerHTML = `${icon}<span>${escapeHtml(message)}</span>`;
  toastContainerEl.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(12px) scale(0.96)";
    toast.style.transition = "all 0.25s ease";
    setTimeout(() => toast.remove(), 260);
  }, 3500);
}
