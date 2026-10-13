# src/routes/health/get_health.py
from src.routes.health import router


@router.get("/health")
def get_health():
    return {"status": "Obsidian Vault Agents läuft."}


# Alias
health_check = get_health
