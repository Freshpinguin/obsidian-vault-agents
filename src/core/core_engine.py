import hashlib
import frontmatter
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.core.logging_config import logger
from src.core.obsidian_processor import PENDING_SUMMARY_TEXT

# The root folder of the vault
WATCH_DIR = os.getenv("WATCH_DIR") or os.getenv("VAULT_PATH") or ("/app/data" if os.path.exists("/app/data") else "./data.example")
# The map is a hidden file as well
MAP_FILE = os.path.join(WATCH_DIR, ".ai_map.json")

def get_content_hash(text: str) -> str:
    """Produces a unique fingerprint (hash) of the text."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def ensure_directory_index(absolute_dir_path: str):
    """Checks whether the folder has an .index.md and creates it (hidden) if not."""
    # Skip the root directory (/app/data); this is only wanted for subfolders
    if absolute_dir_path == WATCH_DIR or absolute_dir_path.endswith(os.sep):
        return
        
    index_file = os.path.join(absolute_dir_path, ".index.md")
    
    if not os.path.exists(index_file):
        rel_dir = os.path.relpath(absolute_dir_path, WATCH_DIR)
        
        # Create an empty file, but with a ready-made YAML header for the AI
        doc = frontmatter.Post("")
        doc.metadata['is_directory_index'] = True
        doc.metadata['folder_name'] = rel_dir
        doc.metadata['ai_summary'] = PENDING_SUMMARY_TEXT
        doc.metadata['last_modified'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(doc))
            logger.info(f"[Core] Hidden .index.md created for folder: {rel_dir}")
        except Exception as e:
            logger.error(f"Error creating {index_file}: {e}")

def update_ai_map(absolute_file_path: str):
    """Updates the JSON map with files and folders."""
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

    ai_map["files"][rel_path] = PENDING_SUMMARY_TEXT

    if rel_dir and rel_dir != ".":
        if rel_dir not in ai_map["directories"]:
            ai_map["directories"][rel_dir] = PENDING_SUMMARY_TEXT

    with open(MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(ai_map, f, indent=2, ensure_ascii=False)
    
    logger.info(f"[Core] AI map updated for: {rel_path}")

def process_document(file_path: str):
    """Called when the watchdog notices a change."""
    
    filename = os.path.basename(file_path)
    
    # IMPORTANT: ignore everything starting with a dot (.) to prevent endless loops.
    if not file_path.endswith('.md') or '.sync-conflict' in file_path or filename.startswith('.') or filename.startswith('_'):
        return

    try:
        doc = frontmatter.load(file_path)
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
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
        logger.info(f"[Core] Metadata updated for: {filename}")

        # 1. Ensure the folder has its hidden index file
        ensure_directory_index(os.path.dirname(file_path))

        # 2. Update the central (now hidden) JSON map
        update_ai_map(file_path)

    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")