# Verwende ein offizielles Python-Image als Basis-Image
FROM python:3.12-slim-buster

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopiere die requirements.txt in das Arbeitsverzeichnis
COPY requirements.txt .

# Installiere die Python-Abhängigkeiten
RUN pip install --no-cache-dir -r requirements.txt

# Führe die Datenbankmigration aus (Tabellen erstellen)
# Dies stellt sicher, dass db.create_all() ausgeführt wird, bevor die App startet
# KORRIGIERTE ZEILE: Manuelles Pushen/Poppen des App-Kontextes
RUN python -c "from app import app, db; app.app_context().push(); db.create_all(); app.app_context().pop()"

# Kopiere den Rest des Anwendungscodes in das Arbeitsverzeichnis
COPY . .

# Definiere den Befehl zum Starten der Anwendung
# Cloud Run erwartet, dass die Anwendung auf dem durch die Umgebungsvariable PORT definierten Port lauscht
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
