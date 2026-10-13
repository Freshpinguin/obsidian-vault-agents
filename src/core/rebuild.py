import os
from dotenv import load_dotenv

load_dotenv()

from src.core.core_engine import ensure_directory_index, update_ai_map

WATCH_DIR = os.getenv("WATCH_DIR") or os.getenv("VAULT_PATH") or ("/app/data" if os.path.exists("/app/data") else "./data.example")

def rebuild_universe():
    print(f"🚀 Starting full scan in {WATCH_DIR}...")
    
    for root, dirs, files in os.walk(WATCH_DIR):
        # Skip hidden folders (such as .obsidian or .stversions) entirely
        dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('_')]
        
        # Ensure an .index.md exists for every folder found
        ensure_directory_index(root)
        
        for file in files:
            # Only include real, visible Markdown files in the map
            if file.endswith('.md') and not file.startswith('.') and not '.sync-conflict' in file:
                file_path = os.path.join(root, file)
                update_ai_map(file_path)
                
    print("✅ Full scan complete. The .ai_map.json and all .index.md files are ready.")

if __name__ == "__main__":
    rebuild_universe()