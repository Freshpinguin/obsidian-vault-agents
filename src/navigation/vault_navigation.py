# src/navigation/vault_navigation.py
"""Navigations-Werkzeuge für den Librarian-Agenten.

Ausgegeben wird immer der vollständige Vault-Pfad, d.h. der Pfad ab dem
data-Verzeichnis (z.B. "Technologie/Militärtechnik/Sensoren, Ortung und Tarnung.md").
Entgegengenommen wird dagegen absichtlich viel mehr: Ein Pfad muss nicht exakt
stimmen, damit ein Aufruf gelingt (siehe _resolve). Der Agent kann also auch mit
einem bloßen Dateinamen, einer anderen Groß-/Kleinschreibung oder einem
unvollständigen Pfad arbeiten und bekommt in der Antwort den kanonischen Pfad
zurück, mit dem er weiternavigieren kann.
"""
import difflib
import json
import os
import unicodedata
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from src.core.obsidian_processor import FRONTMATTER_PATTERN, is_summarizable_path
from src.core.logging_config import logger

PENDING_SUMMARY_TEXT = "Zusammenfassung ausstehend..."

VAULT_ROOT = Path(os.getenv("WATCH_DIR") or os.getenv("VAULT_PATH") or ("/app/data" if os.path.exists("/app/data") else "./data.example")).resolve()

# Vault-Root-Bezeichner, die ein Agent einem Pfad voranstellen könnte
# ("/app/data/Technologie", "data/Technologie", "./vault/Technologie", ...)
ROOT_ALIASES = {"app", "data", "data.example", "vault", "wiki", "obsidian"}

# Wie viele Alternativen bei mehrdeutiger Eingabe genannt werden
MAX_SUGGESTIONS = 8

# Umlaut-Umschreibungen (ä -> ae), damit "Militaertechnik" den Ordner
# "Militärtechnik" findet. ß deckt bereits casefold() ab.
UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "æ": "ae", "ø": "oe", "å": "aa"})

# Ab welcher Ähnlichkeit ein Name als Tippfehler-Treffer gilt (letzte Suchstufe)
TYPO_THRESHOLD = 0.8


class VaultPathError(ValueError):
    """Ein Pfad konnte im Vault nicht (eindeutig) aufgelöst werden.

    'candidates' ist bei mehrdeutigen Eingaben mit den möglichen Vault-Pfaden gefüllt.
    """

    def __init__(self, message: str, candidates: list[str] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


def _vault_root(vault_root: Path | None = None) -> Path:
    return Path(vault_root) if vault_root else VAULT_ROOT


def _norm(text: str) -> str:
    """Vereinheitlicht Schreibweise für den Vergleich: Unicode-Normalform (wichtig
    bei Umlauten, die je nach Sync-Quelle als NFC oder NFD im Dateisystem landen),
    Slash-Richtung, Groß-/Kleinschreibung und umgebende Slashes."""
    text = unicodedata.normalize("NFC", str(text)).replace("\\", "/").strip()
    return text.strip("/").casefold()


def _fold(text: str) -> str:
    """Wie _norm, zusätzlich ohne Umlaute und Akzente ("Militärtechnik" ->
    "militaertechnik"), damit auch ASCII-Umschreibungen eines Namens treffen."""
    folded = _norm(text).translate(UMLAUT_MAP)
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _vault_path(target: Path, vault_root: Path | None = None) -> str:
    """Vollständiger Pfad ausgehend vom data-Verzeichnis, POSIX-Schreibweise."""
    root = _vault_root(vault_root).resolve()
    rel = target.resolve().relative_to(root).as_posix()
    return rel if rel != "." else ""


def _candidate_paths(root: Path, expect: str | None) -> list[Path]:
    """Alle in Frage kommenden Einträge des Vaults (Ordner bzw. Markdown-Dateien)."""
    candidates: list[Path] = []
    if expect != "file":
        candidates.append(root)
    for entry in root.rglob("*"):
        if ".git" in entry.parts:
            continue
        if entry.is_dir():
            if expect != "file":
                candidates.append(entry)
        elif entry.suffix == ".md" and expect != "dir":
            # explizit angefragte .index.md/.ai_map-Nachbarn sind über den
            # direkten Pfad erreichbar; für die Suche zählen echte Notizen.
            if is_summarizable_path(entry):
                candidates.append(entry)
    return candidates


def _strip_root_prefix(segments: list[str]) -> list[str]:
    """Entfernt vorangestellte Root-Bezeichner wie "app/data/" oder "data/"."""
    while len(segments) > 1 and _norm(segments[0]) in ROOT_ALIASES:
        segments = segments[1:]
    return segments


def _fuzzy_resolve(raw: str, root: Path, expect: str | None) -> Path:
    """Sucht den passenden Vault-Eintrag, wenn der Pfad nicht wortwörtlich existiert.

    Stufenweise von streng nach tolerant; die erste Stufe mit genau einem Treffer
    gewinnt. Mehrere Treffer melden die Alternativen, damit der Agent nachschärfen
    kann, statt stillschweigend die falsche Datei zu bekommen.
    """
    segments = _strip_root_prefix([s for s in _norm(raw).split("/") if s not in ("", ".")])
    if not segments:
        return root

    needle = "/".join(segments)
    tail = segments[-1]
    tail_stem = tail[:-3] if tail.endswith(".md") else tail
    # Suchbegriffe mit und ohne .md-Endung, jeweils normalisiert und umlaut-gefaltet
    needles = {needle, f"{needle}.md"} if not needle.endswith(".md") else {needle, needle[:-3]}
    needles_folded = {_fold(n) for n in needles}
    tail_folded = _fold(tail_stem)

    entries = [
        (c, _norm(vp), _norm(c.stem), _fold(vp), _fold(c.stem))
        for c in _candidate_paths(root, expect)
        for vp in [_vault_path(c, root)]
    ]

    stages = [
        # 1. vollständiger Pfad, ggf. mit ergänzter/entfernter .md-Endung
        lambda vp, stem, vp_f, stem_f: vp in needles,
        # 2. Pfad-Ende: "Militärtechnik/Sensoren..." findet den Eintrag darunter
        lambda vp, stem, vp_f, stem_f: any(vp.endswith(f"/{n}") for n in needles),
        # 3. reiner Name/Stem: "Sensoren, Ortung und Tarnung"
        lambda vp, stem, vp_f, stem_f: stem == tail_stem,
        # 4. wie 1-3, aber umlaut-gefaltet: "technologie/militaertechnik"
        lambda vp, stem, vp_f, stem_f: (
            vp_f in needles_folded
            or any(vp_f.endswith(f"/{n}") for n in needles_folded)
            or stem_f == tail_folded
        ),
        # 5. Teilstring im Namen: "Sensoren"
        lambda vp, stem, vp_f, stem_f: tail_stem in stem or tail_folded in stem_f,
        # 6. Teilstring irgendwo im Pfad
        lambda vp, stem, vp_f, stem_f: needle in vp or tail_folded in vp_f,
    ]

    for matches_stage in stages:
        hits = [c for c, *fields in entries if matches_stage(*fields)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise _ambiguous(raw, hits, root)

    # 7. letzte Stufe: Tippfehler im Namen über Ähnlichkeit abfangen
    scored = [
        (difflib.SequenceMatcher(None, tail_folded, stem_f).ratio(), c)
        for c, vp, stem, vp_f, stem_f in entries
    ]
    best = max(scored, key=lambda s: s[0], default=(0.0, None))
    if best[0] >= TYPO_THRESHOLD:
        near_best = [c for score, c in scored if score >= best[0] - 0.01]
        if len(near_best) > 1:
            raise _ambiguous(raw, near_best, root)
        return best[1]

    kind = {"dir": "Kein Ordner", "file": "Keine Datei"}.get(expect, "Kein Eintrag")
    raise VaultPathError(
        f"{kind} zu '{raw}' im Vault gefunden. "
        f"load_ai_map() listet alle vorhandenen Pfade."
    )


def _ambiguous(raw: str, hits: list[Path], root: Path) -> VaultPathError:
    """Fehler mit Auswahlliste, damit der Agent nachschärfen kann, statt
    stillschweigend den falschen Eintrag zu bekommen."""
    options = sorted(_vault_path(h, root) or "(Vault-Root)" for h in hits)
    shown = ", ".join(f"'{o}'" for o in options[:MAX_SUGGESTIONS])
    more = f" (+{len(options) - MAX_SUGGESTIONS} weitere)" if len(options) > MAX_SUGGESTIONS else ""
    return VaultPathError(
        f"'{raw}' ist nicht eindeutig. Gemeint sein könnte: {shown}{more}. "
        f"Bitte mit dem vollständigen Vault-Pfad erneut anfragen.",
        candidates=options,
    )


def _direct_path(raw: str, root: Path) -> Path | None:
    """Wortwörtliche Auflösung: Vault-Pfad, führender Slash, Backslashes oder ein
    absoluter Pfad im Vault. Gibt None zurück, wenn das nichts Existierendes
    innerhalb des Vaults trifft — Pfade, die herausführen ("../../etc/passwd"),
    werden hier verworfen und tauchen auch in der Fuzzy-Suche nie auf."""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / raw.lstrip("/")

    try:
        resolved = candidate.resolve()
    except OSError:
        return None

    if resolved != root and root not in resolved.parents:
        return None
    return resolved if resolved.exists() else None


def _resolve(path: str | Path, vault_root: Path | None = None, expect: str | None = None) -> Path:
    """Löst eine Pfad-Angabe in einen echten Pfad im Dateisystem auf.

    Zuerst wortwörtlich (siehe _direct_path); trifft das nichts Passendes, übernimmt
    _fuzzy_resolve die tolerante Suche (Teilpfad, bloßer Dateiname, andere
    Groß-/Kleinschreibung, fehlende .md-Endung, Umlaut-Umschreibung, Tippfehler).

    'expect' schränkt auf "dir" bzw. "file" ein und macht die Suche damit treffsicherer.
    Ergebnis ist immer ein existierender Eintrag innerhalb des Vaults.
    """
    root = _vault_root(vault_root).resolve()
    raw = unicodedata.normalize("NFC", str(path)).replace("\\", "/").strip()

    if raw.strip("/") in ("", "."):
        if expect == "file":
            raise VaultPathError("Für eine Datei wird ein Pfad benötigt, nicht der Vault-Root.")
        return root

    direct = _direct_path(raw, root)
    if direct is not None:
        if direct.is_dir() and expect != "file":
            return direct
        if direct.is_file() and expect != "dir":
            return direct

    target = _fuzzy_resolve(raw, root, expect)
    logger.info(f"[Navigation] Pfad '{path}' aufgelöst zu '{_vault_path(target, root)}'")
    return target


def _resolve_any(path: str | Path, vault_root: Path | None = None, prefer: str = "file") -> Path:
    """Wie _resolve, aber ohne feste Erwartung: Ein wortwörtlich existierender Pfad
    gewinnt immer (auch wenn er der jeweils andere Typ ist), danach wird der
    bevorzugte Typ gesucht und erst zuletzt der andere. So schlägt der Ordner
    "Technologie" die Datei "Computertechnologie und Zielunterstützung.md",
    während ein bloßer Dateiname weiterhin gefunden wird.
    """
    root = _vault_root(vault_root).resolve()
    raw = unicodedata.normalize("NFC", str(path)).replace("\\", "/").strip()

    if raw.strip("/") in ("", "."):
        return root

    direct = _direct_path(raw, root)
    if direct is not None:
        return direct

    other = "dir" if prefer == "file" else "file"
    try:
        return _resolve(path, root, expect=prefer)
    except VaultPathError as prefer_error:
        try:
            return _resolve(path, root, expect=other)
        except VaultPathError as other_error:
            # Eine Auswahlliste hilft dem Agenten mehr als ein bloßes "nicht gefunden".
            raise other_error if other_error.candidates else prefer_error


def _read_md(filepath: Path) -> tuple[dict, str]:
    """Liest eine Markdown-Datei und trennt Frontmatter und Inhalt."""
    if not filepath.exists():
        return {}, ""

    content = filepath.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return {}, content.strip()

    try:
        return yaml.safe_load(match.group(1)) or {}, match.group(2).strip()
    except yaml.YAMLError as e:
        logger.error(f"[Navigation] YAML Parse-Fehler in {filepath}: {e}")
        return {}, content.strip()


def _strip_frontmatter(text: str) -> str:
    """Entfernt ein eventuell vorhandenes YAML-Frontmatter (---...---) vom Anfang eines
    Textes und gibt nur den Inhalt darunter zurück. No-Op, wenn keins vorhanden ist.
    Wird auch defensiv auf Agenten-Eingaben angewendet (siehe vault_mutation.edit_file),
    damit ein versehentlich mitgeschicktes altes Frontmatter nicht doppelt landet."""
    match = FRONTMATTER_PATTERN.match(text)
    return match.group(2).strip() if match else text.strip()


def load_ai_map(vault_root: Path | None = None) -> dict:
    """Gibt den Inhalt der zentralen .ai_map.json zurück.

    Struktur: {"directories": {vault_pfad: kurz_summary}, "files": {vault_pfad: kurz_summary}}
    """
    ai_map_path = _vault_root(vault_root) / ".ai_map.json"
    if not ai_map_path.exists():
        logger.error(f"[Navigation] .ai_map.json nicht gefunden: {ai_map_path}")
        return {"directories": {}, "files": {}}

    try:
        with open(ai_map_path, "r", encoding="utf-8") as f:
            ai_map = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"[Navigation] .ai_map.json ist ungültig: {e}")
        return {"directories": {}, "files": {}}

    ai_map.setdefault("directories", {})
    ai_map.setdefault("files", {})
    return ai_map


def load_directory_summary(path: str | Path, vault_root: Path | None = None) -> str:
    """Gibt die ausführliche Zusammenfassung eines Ordners (ai_summary der .index.md)
    zusammen mit den Kurz-Zusammenfassungen aller enthaltenen Dateien und Unterordner
    zurück. Jede Zeile nennt den vollständigen Vault-Pfad des Eintrags.

    Der Pfad muss nicht exakt stimmen (siehe _resolve); zeigt er auf eine Datei,
    wird deren Ordner ausgegeben.
    """
    root = _vault_root(vault_root)
    hint = ""
    try:
        target = _resolve_any(path, root, prefer="dir")
    except VaultPathError as e:
        return f"Fehler: {e}"

    # Zeigt die Angabe auf eine Datei, ist der Ordner darüber die sinnvollste Antwort.
    folder = target if target.is_dir() else target.parent
    if not target.is_dir():
        hint = f"> Hinweis: '{path}' ist die Datei '{_vault_path(target, root)}' — unten steht ihr Ordner.\n"

    ai_map = load_ai_map(root)
    files_map = ai_map["files"]
    dirs_map = ai_map["directories"]

    index_fm, _ = _read_md(folder / ".index.md")
    folder_label = _vault_path(folder, root) or "(Vault-Root)"

    sections = [
        f"{hint}# Ordner: {folder_label}",
        "",
        "## Zusammenfassung",
        index_fm.get("ai_summary", PENDING_SUMMARY_TEXT),
    ]

    file_lines = []
    dir_lines = []
    for entry in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        entry_path = _vault_path(entry, root)
        if entry.is_dir():
            sub_fm, _ = _read_md(entry / ".index.md")
            summary = sub_fm.get("ai_summary") or dirs_map.get(entry_path, PENDING_SUMMARY_TEXT)
            dir_lines.append(f"- `{entry_path}/` — {summary}")
        elif is_summarizable_path(entry):
            summary = files_map.get(entry_path, PENDING_SUMMARY_TEXT)
            file_lines.append(f"- `{entry_path}` — {summary}")

    sections += ["", "## Dateien in diesem Ordner"]
    sections += file_lines or ["(keine)"]
    sections += ["", "## Unterordner"]
    sections += dir_lines or ["(keine)"]

    return "\n".join(sections)


def load_file_summary(path: str | Path, vault_root: Path | None = None) -> str:
    """Gibt die ai_summary einer Datei zurück (aus deren YAML-Frontmatter).

    Der Pfad muss nicht exakt stimmen (siehe _resolve); zeigt er auf einen Ordner,
    kommt dessen Zusammenfassung aus der .index.md zurück.
    """
    root = _vault_root(vault_root)
    try:
        target = _resolve_any(path, root, prefer="file")
    except VaultPathError as e:
        return f"Fehler: {e}"

    if target.is_dir():
        target = target / ".index.md"

    fm, _ = _read_md(target)
    return fm.get("ai_summary") or PENDING_SUMMARY_TEXT


def load_file(path: str | Path, vault_root: Path | None = None) -> str:
    """Lädt den Inhalt einer Datei aus dem Vault OHNE das YAML-Frontmatter – das ist nur
    für load_file_summary/load_directory_summary relevant, nicht für den eigentlichen
    Dokumenteninhalt (und darf insbesondere nicht ungefiltert an edit_file zurückgehen,
    sonst verdoppelt sich das Frontmatter beim nächsten Schreiben).

    Der Pfad muss nicht exakt stimmen (siehe _resolve); zeigt er auf einen Ordner,
    kommt der Inhalt von dessen .index.md zurück.
    """
    root = _vault_root(vault_root)
    try:
        filepath = _resolve_any(path, root, prefer="file")
    except VaultPathError as e:
        return f"Fehler: {e}"

    if filepath.is_dir():
        filepath = filepath / ".index.md"
        if not filepath.is_file():
            return f"Fehler: Ordner '{path}' hat noch keine .index.md."

    _, content = _read_md(filepath)
    return content


def _batch(paths: list[str], loader) -> str:
    """Wendet eine der load_*-Funktionen auf mehrere Pfade an und fügt die Ergebnisse
    mit einer Trennzeile pro Pfad zusammen, damit ein einziger Tool-Aufruf mehrere
    Ordner/Dateien auf einmal liefern kann, statt sie einzeln nacheinander abzufragen."""
    if not paths:
        return "Fehler: keine Pfade angegeben."
    return "\n\n".join(f"===== Angefragt: '{p}' =====\n{loader(p)}" for p in paths)


def format_ai_map(ai_map: dict[str, dict[str, str]]) -> str:
    """Formatiert das Ergebnis von load_ai_map() als kompakte Markdown-Übersicht aller
    Ordner und Dateien mit Kurz-Zusammenfassung – der übliche Recherche-Ausgangspunkt,
    den Agenten von Anfang an im Kontext bekommen (siehe Librarian, Chat)."""
    lines = ["## Ordner", ""]
    lines += [f"- `{path}/` — {summary}" for path, summary in sorted(ai_map["directories"].items())] or ["(keine)"]
    lines += ["", "## Dateien", ""]
    lines += [f"- `{path}` — {summary}" for path, summary in sorted(ai_map["files"].items())] or ["(keine)"]
    return "\n".join(lines)


def load_directory_summaries(paths: list[str], vault_root: Path | None = None) -> str:
    """Wie load_directory_summary, aber für mehrere Ordner in einem Aufruf."""
    return _batch(paths, lambda p: load_directory_summary(p, vault_root))


def load_file_summaries(paths: list[str], vault_root: Path | None = None) -> str:
    """Wie load_file_summary, aber für mehrere Dateien in einem Aufruf."""
    return _batch(paths, lambda p: load_file_summary(p, vault_root))


def load_files(paths: list[str], vault_root: Path | None = None) -> str:
    """Wie load_file, aber für mehrere Dateien in einem Aufruf."""
    return _batch(paths, lambda p: load_file(p, vault_root))
