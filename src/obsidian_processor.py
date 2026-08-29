# src/obsidian_processor.py
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime
import yaml  # pip install pyyaml

from src.llm_engine import run_agent_session
from src.agents.summarizer import SummarizerAgent
from src.agents.folder_summarizer import FolderSummarizerAgent
from src.logging_config import logger

# Regex zum sauberen Extrahieren des Obsidian YAML-Frontmatters
FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)

# Regex für Obsidian-Wikilinks: [[Ziel]], [[Ziel|Anzeigetext]], [[Ziel#Abschnitt|Anzeigetext]]
WIKILINK_PATTERN = re.compile(r"\[\[(.+?)\]\]")


def get_content_hash(text: str) -> str:
    """Fingerabdruck des reinen Dokumenteninhalts (ohne Frontmatter)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def is_summarizable_path(filepath: Path) -> bool:
    """Filtert Systemdateien (versteckte/Index-/Sync-Konflikt-Dateien) heraus,
    die nie eigenständig zusammengefasst werden sollen."""
    name = filepath.name
    if filepath.suffix != ".md":
        return False
    if ".sync-conflict" in name:
        return False
    if name.startswith(".") or name.startswith("_"):
        return False
    if name == "CLAUDE.md":
        return False
    return True


def build_note_index(vault_root: Path) -> dict[str, str]:
    """Baut eine Zuordnung Notiz-Name -> relativer Pfad für den gesamten Vault,
    damit Wikilink-Ziele auf echte Dateien aufgelöst werden können."""
    index: dict[str, str] = {}
    for md_file in vault_root.rglob("*.md"):
        if not is_summarizable_path(md_file):
            continue
        index.setdefault(md_file.stem, md_file.relative_to(vault_root).as_posix())
    return index


def extract_linked_files(vault_root: Path, text: str) -> list[str]:
    """Extrahiert alle Obsidian-Wikilinks ([[Ziel]], [[Ziel|Text]], [[Ziel#Abschnitt]])
    aus dem Inhalt und löst sie, wo möglich, auf die tatsächliche Datei im Vault auf."""
    note_index = build_note_index(vault_root)
    linked_files = []
    seen = set()

    for raw_target in WIKILINK_PATTERN.findall(text):
        target = raw_target.split("|")[0].split("#")[0].strip()
        if not target or target in seen:
            continue
        seen.add(target)
        linked_files.append(note_index.get(target, target))

    return linked_files


def build_file_map_content(vault_root: Path, folder_path: Path, ai_map: dict) -> str:
    """Baut eine kleine Markdown-Liste aller Dateien in diesem Ordner (eine Zeile
    pro Datei) mit deren jeweils aktuell in der .ai_map.json hinterlegter Zusammenfassung."""
    files_map = ai_map.get("files", {})
    lines = []
    for entry in sorted(folder_path.iterdir(), key=lambda p: p.name.lower()):
        if not is_summarizable_path(entry):
            continue
        rel_path = entry.relative_to(vault_root).as_posix()
        summary = files_map.get(rel_path, "Zusammenfassung ausstehend...")
        lines.append(f"- **{entry.name}** — {summary}")

    if not lines:
        return ""

    return "## 📂 Dateien in diesem Ordner\n\n" + "\n".join(lines)


class ObsidianVaultManager:
    """Kapselt die Lese- und Schreibzugriffe auf den Obsidian Vault."""

    def __init__(self, vault_root: Path):
        self.vault_root = vault_root
        self.ai_map_path = vault_root / ".ai_map.json"

    def _read_md_file(self, filepath: Path) -> tuple[dict, str]:
        """Liest eine Markdown-Datei und trennt Frontmatter und Inhalt."""
        if not filepath.exists():
            return {}, ""

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        match = FRONTMATTER_PATTERN.match(content)
        if match:
            try:
                frontmatter = yaml.safe_load(match.group(1)) or {}
                text = match.group(2).strip()
                return frontmatter, text
            except yaml.YAMLError as e:
                logger.error(f"YAML Parse-Fehler in {filepath}: {e}")
                return {}, content
        return {}, content.strip()

    def _write_md_file(self, filepath: Path, frontmatter: dict, content: str):
        """Schreibt Frontmatter und Inhalt sauber im Obsidian-Format zurück."""
        # 'sort_keys=False' behält die Reihenfolge der Keys bei
        fm_yaml = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
        new_content = f"---\n{fm_yaml}---\n{content}\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

    def get_document_data(self, filepath: Path) -> tuple[str, str]:
        """Gibt (Zusammenfassung, reiner_text) des Dokuments zurück."""
        fm, text = self._read_md_file(filepath)
        return fm.get("ai_summary", "Zusammenfassung ausstehend..."), text

    def get_subfolder_summaries(self, folder_path: Path) -> str:
        """Sammelt die ai_summary aus der .index.md jedes direkten Unterordners von folder_path."""
        lines = []
        for entry in sorted(folder_path.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir():
                continue
            index_fm, _ = self._read_md_file(entry / ".index.md")
            if not index_fm:
                continue
            summary = index_fm.get("ai_summary", "Zusammenfassung ausstehend...")
            lines.append(f"- **{entry.name}/** — {summary}")
        return "\n".join(lines)

    def has_content_changed(self, filepath: Path) -> bool:
        """Vergleicht den aktuellen Dokumenteninhalt mit dem zuletzt verarbeiteten Stand.
        Erkennt insbesondere das eigene Zurückschreiben der Zusammenfassung (Frontmatter
        ändert sich, der Inhalt selbst aber nicht) und meldet dafür False."""
        fm, text = self._read_md_file(filepath)
        return get_content_hash(text) != fm.get("content_hash")

    def get_filemap_summary(self, relative_path: str) -> str:
        """Liest die Zusammenfassung aus der zentralen .ai_map.json."""
        if not self.ai_map_path.exists():
            return "Zusammenfassung ausstehend..."

        with open(self.ai_map_path, "r", encoding="utf-8") as f:
            ai_map = json.load(f)

        return ai_map.get("files", {}).get(relative_path, "Zusammenfassung ausstehend...")

    def update_vault_data(self, filepath: Path, result: dict):
        """Aktualisiert Dokumenten-Frontmatter und die zentrale .ai_map.json (Datei-Eintrag)
        basierend auf dem Ergebnis des Summarizer-Agenten. Die Ordner-Ebene (.index.md,
        .ai_map.json-Verzeichniseintrag) wird separat über update_folder_data() gepflegt."""

        # 1. Dokumenten-Frontmatter aktualisieren
        fm, text = self._read_md_file(filepath)
        fm["ai_summary"] = result.get("document_summary")
        fm["content_hash"] = get_content_hash(text)
        fm["linked_files"] = extract_linked_files(self.vault_root, text)
        fm["last_modified"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._write_md_file(filepath, fm, text)

        # 2. Zentrale .ai_map.json aktualisieren (Datei-Eintrag)
        if self.ai_map_path.exists():
            with open(self.ai_map_path, "r", encoding="utf-8") as f:
                ai_map = json.load(f)
        else:
            ai_map = {"directories": {}, "files": {}}

        rel_path = filepath.relative_to(self.vault_root).as_posix()

        if "files" not in ai_map:
            ai_map["files"] = {}
        ai_map["files"][rel_path] = result.get("filemap_summary")

        with open(self.ai_map_path, "w", encoding="utf-8") as f:
            json.dump(ai_map, f, indent=2, ensure_ascii=False)

    def build_folder_summary_input(self, folder_path: Path) -> dict:
        """Baut die Eingabedaten für den FolderSummarizer-Agenten: aktuelle Datei-Map,
        Unterordner-Zusammenfassungen sowie die bisherigen Zusammenfassungen dieses Ordners."""
        if self.ai_map_path.exists():
            with open(self.ai_map_path, "r", encoding="utf-8") as f:
                ai_map = json.load(f)
        else:
            ai_map = {"directories": {}, "files": {}}

        rel_dir = folder_path.relative_to(self.vault_root).as_posix()
        index_fm, _ = self._read_md_file(folder_path / ".index.md")

        return {
            "files_overview": build_file_map_content(self.vault_root, folder_path, ai_map),
            "subfolder_summaries": self.get_subfolder_summaries(folder_path),
            "prev_folder_summary": index_fm.get("ai_summary", "Zusammenfassung ausstehend..."),
            "prev_dirmap_summary": ai_map.get("directories", {}).get(rel_dir, "Zusammenfassung ausstehend..."),
        }

    def update_folder_data(self, folder_path: Path, result: dict):
        """Aktualisiert .index.md (Frontmatter + Datei-Map) und den Verzeichnis-Eintrag
        in der .ai_map.json basierend auf dem Ergebnis des FolderSummarizer-Agenten."""
        if self.ai_map_path.exists():
            with open(self.ai_map_path, "r", encoding="utf-8") as f:
                ai_map = json.load(f)
        else:
            ai_map = {"directories": {}, "files": {}}

        rel_dir = folder_path.relative_to(self.vault_root).as_posix()
        if "directories" not in ai_map:
            ai_map["directories"] = {}
        if rel_dir and rel_dir != ".":
            ai_map["directories"][rel_dir] = result.get("dirmap_summary")

        with open(self.ai_map_path, "w", encoding="utf-8") as f:
            json.dump(ai_map, f, indent=2, ensure_ascii=False)

        index_path = folder_path / ".index.md"
        index_fm, _ = self._read_md_file(index_path)

        index_fm["ai_summary"] = result.get("folder_summary")
        index_fm["folder_name"] = folder_path.name
        index_fm["is_directory_index"] = True
        index_fm["last_modified"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        file_map_content = build_file_map_content(self.vault_root, folder_path, ai_map)
        self._write_md_file(index_path, index_fm, file_map_content)

    def refresh_file_map(self, folder_path: Path):
        """Baut die Datei-Map im Inhalt einer .index.md aus dem aktuellen Stand
        von .ai_map.json neu auf, ohne die Zusammenfassung (Frontmatter) anzufassen.
        Wird von der periodischen Wartung genutzt, damit gelöschte Dateien
        sofort aus der Map verschwinden. Schreibt die Datei NUR, wenn sich die Map
        inhaltlich tatsächlich geändert hat (sonst würde jeder Wartungslauf jede
        .index.md im Vault unnötig neu schreiben und einen Watchdog-Event auslösen)."""
        index_path = folder_path / ".index.md"
        if not index_path.exists():
            return

        ai_map = {"directories": {}, "files": {}}
        if self.ai_map_path.exists():
            with open(self.ai_map_path, "r", encoding="utf-8") as f:
                ai_map = json.load(f)

        index_fm, current_content = self._read_md_file(index_path)
        file_map_content = build_file_map_content(self.vault_root, folder_path, ai_map)
        if file_map_content == current_content:
            return
        self._write_md_file(index_path, index_fm, file_map_content)


def process_obsidian_file(vault_root: Path, filepath: Path) -> bool:
    """
    Die Hauptfunktion, die vom Watchdog aufgerufen wird.

    Gibt zurück, ob sich dadurch die Zusammenfassung des direkten Elternordners
    geändert hat (Grundlage für eine mögliche Kaskade weiter nach oben, siehe
    FolderSummaryScheduler in scheduler.py).
    """
    manager = ObsidianVaultManager(vault_root)

    # Pfad für die Map muss POSIX-Standard (Slashes) nutzen
    rel_path_str = filepath.relative_to(vault_root).as_posix()

    # 1. Daten zusammenziehen
    prev_doc_summary, current_content = manager.get_document_data(filepath)
    prev_filemap_summary = manager.get_filemap_summary(rel_path_str)

    # 2. Input bauen (previous_content lassen wir leer oder übergeben die alte summary)
    input_data = {
        "current_content": current_content,
        "previous_content": "", # Nicht mehr auf Dateisystem-Ebene verfügbar
        "prev_doc_summary": prev_doc_summary,
        "prev_filemap_summary": prev_filemap_summary,
    }

    logger.info(f"[{filepath.name}] Baue Summaries auf Basis von Obsidian-Daten...")

    # 3. Agent ausführen
    session = run_agent_session(agent=SummarizerAgent, raw_input=input_data)

    # 4. Speichern
    if session.is_successful:
        manager.update_vault_data(filepath, session.final_result.model_dump())
        logger.info(f"[{filepath.name}] YAML und .ai_map.json (Datei-Eintrag) aktualisiert!")
        # Die Datei-Zusammenfassung hat sich geändert -> Ordner-Zusammenfassung neu erzeugen lassen.
        return process_folder_summary(vault_root, filepath.parent)

    logger.error(f"[{filepath.name}] Agent Fehler. Vault wurde nicht verändert.")
    return False


def process_folder_summary(vault_root: Path, folder_path: Path) -> bool:
    """
    Wird aufgerufen, nachdem sich die Zusammenfassung einer Datei/eines Unterordners
    in folder_path geändert hat. Ruft den FolderSummarizer-Agenten auf, um die
    .index.md (ausführliche Zusammenfassung) und den Kurz-Eintrag dieses Ordners in
    der .ai_map.json zu aktualisieren.

    Gibt zurück, ob sich folder_summary oder dirmap_summary dadurch tatsächlich
    geändert haben (Grundlage für eine Kaskade zum übergeordneten Ordner).
    """
    manager = ObsidianVaultManager(vault_root)
    rel_dir = folder_path.relative_to(vault_root).as_posix()
    dir_label = rel_dir if rel_dir != "." else "(vault-root)"

    input_data = manager.build_folder_summary_input(folder_path)

    logger.info(f"[{dir_label}] Baue Ordner-Zusammenfassung...")

    session = run_agent_session(agent=FolderSummarizerAgent, raw_input=input_data)

    if not session.is_successful:
        logger.error(f"[{dir_label}] FolderSummarizer-Agent Fehler. Ordner-Zusammenfassung nicht verändert.")
        return False

    result = session.final_result.model_dump()
    changed = (
        result.get("folder_summary") != input_data.get("prev_folder_summary")
        or result.get("dirmap_summary") != input_data.get("prev_dirmap_summary")
    )
    manager.update_folder_data(folder_path, result)
    logger.info(f"[{dir_label}] .index.md und .ai_map.json (Ordner-Eintrag) aktualisiert!")
    return changed
