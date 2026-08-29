# Schlankes, offizielles Python-Image (perfekt für ARM64 / Raspberry Pi 5)
FROM python:3.11-slim

# Verhindert, dass Python .pyc-Dateien schreibt
ENV PYTHONDONTWRITEBYTECODE=1
# Sorgt dafür, dass Log-Ausgaben sofort im Terminal angezeigt werden
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System-Abhängigkeiten installieren (falls du später git oder build-tools für Vektor-DBs brauchst)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python-Pakete installieren
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Nicht-root-User mit derselben UID/GID wie der Host-User (robin, 1000).
# Nötig, damit das gemountete Repo + der gemountete SSH-Key dem Prozess
# "gehören" -- sonst verweigert git ("dubious ownership") bzw. ssh
# ("Bad owner or permissions") die Arbeit an Dateien, die einem anderen
# User gehören (root != Host-UID 1000).
RUN useradd -u 1000 -m -s /bin/bash appuser
USER appuser

# Startbefehl: Uvicorn startet unsere FastAPI-App ("main:app") in src/
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]