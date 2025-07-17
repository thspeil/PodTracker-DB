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

    # Setze den SECRET_KEY_FLASK_LOGIN als Umgebungsvariable (NICHT mehr als ARG, da es nur zur Laufzeit benötigt wird)
    # WICHTIG: Dieser Wert muss weiterhin in Cloud Run als Umgebungsvariable gesetzt sein!
    ENV SECRET_KEY_FLASK_LOGIN=${SECRET_KEY_FLASK_LOGIN}

    # Kopiere das Startup-Skript und mache es ausführbar
    COPY start.sh .
    RUN chmod +x start.sh

    # Definiere den Befehl zum Starten der Anwendung
    # Cloud Run erwartet, dass die Anwendung auf dem durch die Umgebungsvariable PORT definierten Port lauscht
    CMD ["./start.sh"]

    