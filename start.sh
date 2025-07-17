#!/bin/bash

# Führe die Datenbankmigration aus (Tabellen erstellen)
# Dies wird bei jedem Container-Start ausgeführt.
# Es ist idempotent, d.h., es hat keine negativen Auswirkungen, wenn Tabellen bereits existieren.
echo "Running database migrations (db.create_all())..."
python -c "from app import app, db; app.app_context().push(); db.create_all(); app.app_context().pop()"
echo "Database migrations complete."

# Starte die Gunicorn-Anwendung
echo "Starting Gunicorn server..."
exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app