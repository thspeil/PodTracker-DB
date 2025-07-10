# Verwende ein offizielles Python-Laufzeit-Image als Basis
FROM python:3.12-slim-bookworm

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Installiere alle Produktionsabhängigkeiten
# Kopiere zuerst requirements.txt, um Docker-Cache zu nutzen
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere die Python-Anwendung
COPY app.py .

# Kopiere die HTML-Template-Dateien in den Root des Arbeitsverzeichnisses
# Da template_folder='.' ist, müssen diese hier liegen
COPY podcast_tracker-DB.html .
COPY Impressum.html .
COPY Datenschutz.html .

# Kopiere den gesamten static-Ordner in das Arbeitsverzeichnis
# Wichtig: Der Zielpfad 'static/' muss mit einem Schrägstrich enden, um anzuzeigen, dass es ein Verzeichnis ist
COPY static/ static/

# Exponiere den Port, auf dem die Flask-App läuft
EXPOSE 5000

# Starte die Flask-Anwendung mit Gunicorn, wenn der Container startet
# 'app:app' bedeutet, dass die Flask-App-Instanz 'app' aus der Datei 'app.py' verwendet wird
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
