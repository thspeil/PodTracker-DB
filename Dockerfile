# Verwende ein offizielles Python-Laufzeit-Image als Basis
FROM python:3.12-slim-bookworm

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Installiere alle Produktionsabhängigkeiten
# Kopiere zuerst requirements.txt, um Docker-Cache zu nutzen
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere die Flask-Anwendung und die HTML-Dateien
COPY app.py .
COPY podcast_tracker-DB.html .
COPY Impressum.html .
COPY Datenschutz.html .
COPY static/ static/ # NEU: Kopiert den gesamten static-Ordner

# Exponiere den Port, auf dem die Flask-App läuft
EXPOSE 5000

# Starte die Flask-Anwendung mit Gunicorn, wenn der Container startet
# 'app:app' bedeutet, dass die Flask-App-Instanz 'app' aus der Datei 'app.py' verwendet wird
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
