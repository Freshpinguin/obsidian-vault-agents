import hashlib
import frontmatter
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.core.logging_config import logger

# Der Hauptordner deines Wikis
WATCH_DIR = os.getenv("WATCH_DIR") or os.getenv("VAULT_PATH") or ("/app/data" if os.path.exists("/app/data") else "./data.example")
# Die Map ist jetzt auch eine unsichtbare Datei
MAP_FILE = os.path.join(WATCH_DIR, ".ai_map.json")

def get_content_hash(text: str) -> str:
    """Erzeugt einen eindeutigen Fingerabdruck (Hash) des Textes."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def ensure_directory_index(absolute_dir_path: str):
    """Prüft, ob der Ordner eine .index.md hat, und legt sie unsichtbar an."""
    # Wir ignorieren das Hauptverzeichnis (/app/data), wir wollen das nur für Unterordner
    if absolute_dir_path == WATCH_DIR or absolute_dir_path.endswith(os.sep):
        return
        
    index_file = os.path.join(absolute_dir_path, ".index.md")
    
    if not os.path.exists(index_file):
        rel_dir = os.path.relpath(absolute_dir_path, WATCH_DIR)
        
        # Erstelle eine leere Datei, aber mit fertigem YAML-Header für die KI
        doc = frontmatter.Post("")
        doc.metadata['is_directory_index'] = True
        doc.metadata['folder_name'] = rel_dir
        doc.metadata['ai_summary'] = "Ordner-Zusammenfassung ausstehend..."
        doc.metadata['last_modified'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(doc))
            logger.info(f"[Core] Unsichtbare .index.md erstellt für Ordner: {rel_dir}")
        except Exception as e:
            logger.error(f"Fehler beim Erstellen von {index_file}: {e}")

def update_ai_map(absolute_file_path: str):
    """Aktualisiert die JSON-Map mit Dateien und Ordnern."""
    rel_path = os.path.relpath(absolute_file_path, WATCH_DIR)
    rel_dir = os.path.dirname(rel_path)

    if os.path.exists(MAP_FILE):
        try:
            with open(MAP_FILE, 'r', encoding='utf-8') as f:
                ai_map = json.load(f)
        except Exception:
            ai_map = {"directories": {}, "files": {}}
    else:
        ai_map = {"directories": {}, "files": {}}

    if "directories" not in ai_map: ai_map["directories"] = {}
    if "files" not in ai_map: ai_map["files"] = {}

    ai_map["files"][rel_path] = "Zusammenfassung ausstehend..."

    if rel_dir and rel_dir != ".":
        if rel_dir not in ai_map["directories"]:
            ai_map["directories"][rel_dir] = "Zusammenfassung ausstehend..."

    with open(MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(ai_map, f, indent=2, ensure_ascii=False)
    
    logger.info(f"[Core] AI Map aktualisiert für: {rel_path}")

def process_document(file_path: str):
    """Wird aufgerufen, wenn der Watchdog eine Änderung bemerkt."""
    
    filename = os.path.basename(file_path)
    
    # WICHTIG: Ignoriere alles, was mit einem Punkt (.) beginnt, um Endlosschleifen zu verhindern!
    if not file_path.endswith('.md') or '.sync-conflict' in file_path or filename.startswith('.') or filename.startswith('_'):
        return

    try:
        doc = frontmatter.load(file_path)
    except Exception as e:
        logger.error(f"Fehler beim Lesen von {file_path}: {e}")
        return

    content = doc.content
    current_hash = get_content_hash(content)
    saved_hash = doc.metadata.get('content_hash', '')

    if current_hash == saved_hash:
        return
    
    doc.metadata['content_hash'] = current_hash
    doc.metadata['last_modified'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(doc))
        logger.info(f"[Core] Metadaten aktualisiert für: {filename}")

        # 1. Stelle sich‚‚‚er, dass der Ordner seine versteckte Index-Datei hat
        ensure_directory_index(os.path.dirname(file_path))

        # 2. Aktualisiere die zentrale (jetzt versteckte) JSON-Map
        update_ai_map(file_path)

    except Exception as e:
        logger.error(f"Fehler beim Speichern von {file_path}: {e}")