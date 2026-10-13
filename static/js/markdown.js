// ==========================================
// 1. Markdown & Wikilinks Parser
// ==========================================
export function renderMarkdown(md) {
  if (!md) return "";
  // Konvertiere Obsidian-Wikilinks: [[Ziel]] oder [[Ziel|Label]]
  const withWikilinks = md.replace(/\[\[(.*?)\]\]/g, (match, inner) => {
    const parts = inner.split("|");
    const target = parts[0].trim();
    const label = (parts[1] || target).trim();
    return `<a class="wikilink" href="#" data-wikilink="${escapeHtml(target)}" title="Gehe zu '${escapeHtml(target)}'">${escapeHtml(label)}</a>`;
  });

  if (window.marked && typeof window.marked.parse === "function") {
    return window.marked.parse(withWikilinks);
  }

  // Fallback, falls marked.js noch nicht bereit ist
  return `<pre style="white-space: pre-wrap; font-family: inherit;">${escapeHtml(withWikilinks)}</pre>`;
}

export function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
