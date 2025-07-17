# Verwende ein offizielles Python-Image als Basis-Image
FROM python:3.12-slim

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Installiere System-Abhängigkeiten, die für Python-Pakete wie psycopg2-binary benötigt werden
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Kopiere die requirements.txt in das Arbeitsverzeichnis
COPY requirements.txt .

# Installiere die Python-Abhängigkeiten
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere den REST des Anwendungscodes in das Arbeitsverzeichnis
COPY . .

# ERSTELLE EIN TEMPORÄRES SKRIPT FÜR DIE DATENBANKINITIALISIERUNG
RUN echo "from app import app, db; app.app_context().push(); db.create_all(); app.app_context().pop()" > db_init_script.py

# Führe das temporäre Skript aus, um die Datenbanktabellen zu erstellen
RUN python db_init_script.py

# LÖSCHE DAS TEMPORÄRE SKRIPT (optional, um Image-Größe zu optimieren)
RUN rm db_init_script.py

# Definiere den Befehl zum Starten der Anwendung
# Cloud Run erwartet, dass die Anwendung auf dem durch die Umgebungsvariable PORT definierten Port lauscht
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
