# src/navigation/vault_mutation.py
"""Schreibende Gegenstücke zu vault_navigation.py: Ordner/Dateien anlegen, Dateien
bearbeiten und verschieben. Nutzt dieselbe tolerante Pfad-Auflösung (siehe
vault_navigation._resolve) für bereits existierende Ziele (edit_file, move_file-Quelle).
Für NEUE Pfade (create_directory, create_file, move_file-Ziel) gibt es keine Fuzzy-Suche
(nichts zum Abgleichen vorhanden) – dort wird nur normalisiert und gegen ein Verlassen
des Vaults abgesichert (siehe _resolve_new_path).

Schreibt ein Aufruf hier tatsächlich eine Datei im Vault, greift automatisch der bereits
laufende Watchdog (siehe main.py): Er erkennt die Änderung und stößt die normale
Zusammenfassungs-Pipeline an (Summarizer-Agent, .ai_map.json, .index.md-Kaskade) – diese
Funktionen müssen sich darum nicht selbst kümmern.
"""
import unicodedata
from pathlib import Path

import yaml

from src.obsidian_processor import is_summarizable_path
from src.logging_config import logger
from src.navigation.vault_navigation import (
    ROOT_ALIASES,
    VaultPathError,
    _read_md,
    _resolve,
    _strip_frontmatter,
    _vault_path,
    _vault_root,
)


def _resolve_new_path(path: str | Path, vault_root: Path | None = None) -> Path:
    """Löst einen NEUEN (noch nicht existierenden) Vault-Pfad auf: normalisiert
    Schreibweise (Unicode, Slash-Richtung, führende Slashes, vorangestellte
    Root-Bezeichner wie "data/") OHNE Fuzzy-Suche – für neue Pfade gibt es nichts zum
    Abgleichen. Lehnt Pfade ab, die aus dem Vault herausführen würden."""
    root = _vault_root(vault_root).resolve()
    raw = unicodedata.normalize("NFC", str(path)).replace("\\", "/").strip()
    segments = [s for s in raw.strip("/").split("/") if s not in ("", ".")]

    while len(segments) > 1 and segments[0].casefold() in ROOT_ALIASES:
        segments = segments[1:]

    if not segments:
        raise VaultPathError("Es wurde kein Pfad angegeben.")

    resolved = root.joinpath(*segments).resolve()
    if resolved != root and root not in resolved.parents:
        raise VaultPathError(f"Pfad liegt außerhalb des Vaults: {path}")
    return resolved


def create_directory(path: str, vault_root: Path | None = None) -> str:
    """Legt einen neuen (leeren) Ordner im Vault an, inkl. fehlender Zwischenordner."""
    root = _vault_root(vault_root)
    try:
        target = _resolve_new_path(path, root)
    except VaultPathError as e:
        return f"Fehler: {e}"

    if target.exists():
        kind = "Ordner" if target.is_dir() else "Datei"
        return f"Fehler: '{_vault_path(target, root)}' existiert bereits ({kind})."

    target.mkdir(parents=True)
    logger.info(f"[Mutation] Ordner erstellt: {_vault_path(target, root)}")
    return f"Ordner '{_vault_path(target, root)}' wurde erstellt."


def create_file(path: str, content: str, vault_root: Path | None = None) -> str:
    """Legt eine neue Markdown-Datei mit dem gegebenen Inhalt an (ohne Frontmatter –
    das ergänzt die Zusammenfassungs-Pipeline automatisch). Fehlende Zwischenordner
    werden dabei mit angelegt."""
    root = _vault_root(vault_root)
    try:
        target = _resolve_new_path(path, root)
    except VaultPathError as e:
        return f"Fehler: {e}"

    if target.suffix != ".md":
        return f"Fehler: Nur .md-Dateien werden unterstützt ('{path}')."
    if not is_summarizable_path(target):
        return f"Fehler: '{_vault_path(target, root)}' ist kein gültiger Dateiname für eine Notiz."
    if target.exists():
        return f"Fehler: '{_vault_path(target, root)}' existiert bereits."

    target.parent.mkdir(parents=True, exist_ok=True)
    # Defensiv: falls versehentlich ein YAML-Frontmatter im übergebenen Inhalt steckt
    # (z.B. weil ein Agent den Inhalt einer anderen Datei als Vorlage kopiert hat),
    # wird es entfernt statt in der neuen Datei zu landen.
    target.write_text(_strip_frontmatter(content) + "\n", encoding="utf-8")
    logger.info(f"[Mutation] Datei erstellt: {_vault_path(target, root)}")
    return f"Datei '{_vault_path(target, root)}' wurde erstellt."


def edit_file(path: str, content: str, vault_root: Path | None = None) -> str:
    """Ersetzt den Inhalt einer bestehenden Datei (unterhalb des YAML-Frontmatters, das
    unverändert erhalten bleibt – die Zusammenfassungs-Pipeline aktualisiert es beim
    nächsten Durchlauf ohnehin). Der Pfad muss nicht exakt stimmen (siehe _resolve)."""
    root = _vault_root(vault_root)
    try:
        target = _resolve(path, root, expect="file")
    except VaultPathError as e:
        return f"Fehler: {e}"

    if not is_summarizable_path(target):
        return f"Fehler: '{_vault_path(target, root)}' ist eine Systemdatei und kann nicht bearbeitet werden."

    fm, _ = _read_md(target)
    # Defensiv: content kann selbst ein (ggf. veraltetes) Frontmatter enthalten, wenn der
    # Aufrufer z.B. den kompletten alten Dateiinhalt als Vorlage genommen hat - das würde
    # sonst VOR das frisch gelesene, aktuelle Frontmatter geschrieben und sich verdoppeln.
    body = _strip_frontmatter(content)
    if fm:
        fm_yaml = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        new_text = f"---\n{fm_yaml}---\n{body}\n"
    else:
        new_text = body + "\n"

    target.write_text(new_text, encoding="utf-8")
    logger.info(f"[Mutation] Datei bearbeitet: {_vault_path(target, root)}")
    return f"Datei '{_vault_path(target, root)}' wurde aktualisiert."


def move_file(path: str, new_path: str, vault_root: Path | None = None) -> str:
    """Verschiebt/benennt eine bestehende Datei um. Die Quelle wird tolerant aufgelöst
    (siehe _resolve), das Ziel muss ein neuer, noch nicht existierender .md-Pfad sein."""
    root = _vault_root(vault_root)
    try:
        source = _resolve(path, root, expect="file")
    except VaultPathError as e:
        return f"Fehler: {e}"

    if not is_summarizable_path(source):
        return f"Fehler: '{_vault_path(source, root)}' ist eine Systemdatei und kann nicht verschoben werden."

    try:
        destination = _resolve_new_path(new_path, root)
    except VaultPathError as e:
        return f"Fehler: {e}"

    if destination.suffix != ".md":
        return f"Fehler: Ziel muss auf .md enden ('{new_path}')."
    if destination.exists():
        return f"Fehler: '{_vault_path(destination, root)}' existiert bereits."

    source_label = _vault_path(source, root)
    dest_label = _vault_path(destination, root)

    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)
    logger.info(f"[Mutation] Datei verschoben: {source_label} -> {dest_label}")
    return f"Datei verschoben: '{source_label}' -> '{dest_label}'."
