#!/bin/bash

# Führe die Datenbankmigration aus (Tabellen erstellen)
# Dies wird bei jedem Container-Start ausgeführt.
# Es ist idempotent, d.h., es hat keine negativen Auswirkungen, wenn Tabellen bereits existieren.
# Der 'flask init-db' Befehl handhabt den Anwendungskontext automatisch und ist robuster.
echo "Running database migrations (init-db)..."
flask init-db
echo "Database migrations complete."

# Starte die Gunicorn-Anwendung
echo "Starting Gunicorn server..."
exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app