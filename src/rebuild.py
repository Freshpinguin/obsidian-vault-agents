import os
from src.core_engine import ensure_directory_index, update_ai_map

WATCH_DIR = os.getenv("WATCH_DIR", "/app/data")

def rebuild_universe():
    print(f"🚀 Starte vollständigen Scan in {WATCH_DIR}...")
    
    for root, dirs, files in os.walk(WATCH_DIR):
        # Versteckte Ordner (wie .obsidian oder .stversions) komplett überspringen
        dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('_')]
        
        # Für jeden gefundenen Ordner die .index.md sicherstellen
        ensure_directory_index(root)
        
        for file in files:
            # Nur echte, sichtbare Markdown-Dateien in die Map aufnehmen
            if file.endswith('.md') and not file.startswith('.') and not '.sync-conflict' in file:
                file_path = os.path.join(root, file)
                update_ai_map(file_path)
                
    print("✅ Vollständiger Scan abgeschlossen! Die .ai_map.json und alle .index.md Dateien sind bereit.")

if __name__ == "__main__":
    rebuild_universe()