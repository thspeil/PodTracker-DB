import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime, timedelta 
import requests
import xml.etree.ElementTree as ET

# NEUE IMPORTE FÜR FLASK-LOGIN
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Lade Umgebungsvariablen aus .env-Datei (für lokale Entwicklung, in Codespaces durch Secrets überschrieben)
load_dotenv()

# Flask-Anwendung initialisieren
# 'static_folder' verweist auf den Ordner für statische Dateien (CSS, JS, Bilder, Favicon)
# 'template_folder' verweist auf den Ordner für HTML-Templates (hier das Hauptverzeichnis '.')
app = Flask(__name__, static_folder='static', template_folder='.')

# WICHTIG: Ersetze dies durch einen langen, zufälligen und sicheren String!
# Dies ist für die Session-Sicherheit von Flask und Flask-Login unerlässlich.
# Der Key wird jetzt aus der Umgebungsvariable SECRET_KEY_FLASK_LOGIN gelesen.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY_FLASK_LOGIN', 'your_super_secret_key_that_you_must_change_in_production')

# NEU: Konfiguration für die Dauer des "Remember Me"-Cookies
# Wenn der Benutzer "remember me" wählt, bleibt er für diese Dauer eingeloggt.
# Standardmäßig ist es 365 Tage. Hier auf 20 Minuten gesetzt.
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(minutes=20)

# CORS für alle Routen aktivieren (für Entwicklung).\
# In einer Produktionsumgebung sollte dies auf spezifische Ursprünge beschränkt werden.
CORS(app)

# Konfiguration der Datenbank
# Die DATABASE_URL wird aus den Umgebungsvariablen geladen (z.B. GitHub Codespaces Secret)
# Fallback auf SQLite für den Fall, dass DATABASE_URL nicht gesetzt ist (z.B. erster lokaler Test)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'podcast_tracker.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Deaktiviert Warnungen zur Änderungsverfolgung

db = SQLAlchemy(app)

# FLASK-LOGIN INITIALISIERUNG
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Die Route, zu der nicht-authentifizierte Benutzer umgeleitet werden

# Definiere die Fehlermeldung, wenn ein Login erforderlich ist
login_manager.login_message = "Bitte melden Sie sich an, um diese Seite aufzurufen."
login_manager.login_message_category = "warning" # Kategorie für Flash-Nachrichten

# NEUES USER MODELL FÜR FLASK-LOGIN
# Dieses Modell repräsentiert einen Benutzer. Für den Anfang nutzen wir einen festen Benutzer.
# Später solltest du dies mit deiner Datenbank verbinden (z.B. eine neue User-Tabelle).
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    # Diese statische Methode würde normalerweise den Benutzer aus der Datenbank laden
    @staticmethod
    def get_user_by_username(username):
        if username == "user1": # Benutzernamen geändert auf "user1"
            # HIER DEINEN GENERIERTEN HASH FÜR "SpeilPW" EINFÜGEN
            # Beispiel-Hash für "SpeilPW" (ERSETZE DIES DURCH DEINEN GENERIERTEN HASH!)
            hashed_pw_for_user1 = "scrypt:32768:8:1$anilOJC7MTH87cwT$624d07e2737d25657bff2e6d516bd38cdee48729cd9421b22b8f6a30f3e49a3627e3a334718f84216a6698bf0c55a21043f63fe4c73c9007ae212d6d657929d3" # <--- HIER DEINEN GENERIERTEN HASH EINFÜGEN
            return User(id=1, username="user1", password_hash=hashed_pw_for_user1)
        return None

    # Flask-Login benötigt diese Methode, um die ID des Benutzers abzurufen
    def get_id(self):
        return str(self.id)

# Dies ist ein Callback, der von Flask-Login verwendet wird, um einen Benutzer anhand seiner ID zu laden.
@login_manager.user_loader
def load_user(user_id):
    if user_id == '1':
        # Muss zum oben definierten User passen
        hashed_pw_for_user1 = "scrypt:32768:8:1$anilOJC7MTH87cwT$624d07e2737d25657bff2e6d516bd38cdee48729cd9421b22b8f6a30f3e49a3627e3a334718f84216a6698bf0c55a21043f63fe4c73c9007ae212d6d657929d3" # <--- HIER DEN GLEICHEN GENERIERTEN HASH EINFÜGEN
        return User(id=1, username="user1", password_hash=hashed_pw_for_user1)
    return None


# Definition des Datenmodells für Podcast-Feeds
class PodcastFeed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Die URL des RSS-Feeds, muss einzigartig sein und darf nicht leer sein
    url = db.Column(db.String(500), unique=True, nullable=False)
    # Name des Podcasts (optional, kann aus XLSX oder Feed stammen)
    name = db.Column(db.String(255))
    # Optionales Thema des Podcasts
    topic = db.Column(db.String(255))
    # Aktiv-Status des Feeds
    is_active = db.Column(db.Boolean, default=True)
    # Zeitpunkt der letzten Aktualisierung des Feeds
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    # Beziehung zu den Episoden: Ein Feed hat viele Episoden
    # 'cascade="all, delete-orphan"' löscht Episoden, wenn der zugehörige Feed gelöscht wird
    episodes = db.relationship('Episode', backref='feed', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<PodcastFeed {self.url}>'

# Definition des Datenmodells für Episoden
class Episode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Fremdschlüssel zur Verknüpfung mit dem PodcastFeed
    feed_id = db.Column(db.Integer, db.ForeignKey('podcast_feed.id'), nullable=False)
    # Titel der Episode
    title = db.Column(db.String(500), nullable=False)
    # Beschreibung der Episode (kann lang sein)
    description = db.Column(db.Text)
    # Veröffentlichungsdatum der Episode (als DateTime-Objekt für einfachere Sortierung)
    pub_date = db.Column(db.DateTime)
    # Permalink oder URL der Episode, muss einzigartig sein und darf nicht leer sein
    url = db.Column(db.String(500), unique=True, nullable=False)
    # Feld für den Favoritenstatus
    is_favorite = db.Column(db.Boolean, default=False)
    # Feld für den Host/Autor der Episode
    host = db.Column(db.String(255))

    def __repr__(self):
        return f'<Episode {self.title}>'

# Hilfsfunktion zum Parsen von RSS-Feeds
def parse_rss_feed(feed_url):
    """
    Ruft einen RSS-Feed ab und parst ihn, um Episodendaten zu extrahieren.
    """
    try:
        response = requests.get(feed_url, timeout=10)
        response.raise_for_status() # Löst einen HTTPError für schlechte Antworten (4xx oder 5xx) aus
        
        # XML-Inhalt parsen
        root = ET.fromstring(response.content)
        
        episodes_data = []
        # Namespace für iTunes-Tags
        itunes_ns = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

        # Finde alle 'item'-Elemente im RSS-Feed (Episoden)
        for item in root.findall('.//item'):
            title = item.find('title').text if item.find('title') is not None else 'No Title'
            description = item.find('description').text if item.find('description') is not None else 'No Description'
            pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else None
            
            # Versuche, die Episode-URL zu finden (entweder enclosure url oder link)
            episode_url = None
            enclosure = item.find('enclosure')
            if enclosure is not None and 'url' in enclosure.attrib:
                episode_url = enclosure.attrib['url']
            elif item.find('link') is not None:
                episode_url = item.find('link').text

            # Host/Autor extrahieren
            host = None
            # Versuche itunes:author
            itunes_author = item.find('itunes:author', itunes_ns)
            if itunes_author is not None:
                host = itunes_author.text
            # Fallback auf Standard-Author-Tag
            elif item.find('author') is not None:
                host = item.find('author').text

            pub_date = None
            if pub_date_str:
                try:
                    # Versuche, Datumsformate zu parsen (RFC 822 ist üblich für RSS)
                    pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
                except ValueError:
                    try:
                        # Versuche ein alternatives Format, falls das erste fehlschlägt
                        pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z') # Mit UTC-Offset
                    except ValueError:
                        print(f"Warnung: Datum konnte nicht geparst werden: {pub_date_str}")
                        pass # Datum bleibt None, wenn Parsen fehlschlägt

            if episode_url: # Nur Episoden mit einer URL hinzufügen
                episodes_data.append({
                    'title': title,
                    'description': description,
                    'pub_date': pub_date,
                    'url': episode_url,
                    'host': host
                })
        return episodes_data
    except requests.exceptions.RequestException as e:
        print(f"Fehler beim Abrufen des Feeds {feed_url}: {e}")
        return None
    except ET.ParseError as e:
        print(f"Fehler beim Parsen des XML-Feeds {feed_url}: {e}")
        return None
    except Exception as e:
        print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        return None

# NEUE ROUTEN FÜR FLASK-LOGIN

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('serve_frontend')) # Wenn bereits angemeldet, zur Hauptseite umleiten

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.get_user_by_username(username) # Versuche, den Benutzer zu laden

        if user and check_password_hash(user.password_hash, password):
            login_user(user) # Benutzer einloggen
            flash('Erfolgreich eingeloggt!', 'success')
            # Weiterleitung zur ursprünglich angeforderten Seite oder zur Hauptseite
            next_page = request.args.get('next')
            return redirect(next_page or url_for('serve_frontend'))
        else:
            flash('Ungültiger Benutzername oder Passwort.', 'danger')
    return render_template('login.html') # Rendere das Login-Formular

@app.route('/logout')
@login_required # Nur eingeloggte Benutzer können sich ausloggen
def logout():
    logout_user() # Benutzer ausloggen
    flash('Erfolgreich ausgeloggt.', 'info')
    return redirect(url_for('login')) # Zur Login-Seite umleiten

# API-Endpunkte

# Route zum Servieren der Haupt-HTML-Datei (Frontend) - JETZT GESCHÜTZT!
@app.route('/')
@login_required # Diese Route ist jetzt nur für eingeloggte Benutzer zugänglich
def serve_frontend():
    # Stellt die podcast_tracker-DB.html bereit, die im template_folder (root) liegt
    return render_template('podcast_tracker-DB.html')

# Route für Impressum - NICHT GESCHÜTZT
@app.route('/impressum')
def impressum():
    # Stellt die Impressum.html bereit, die im template_folder (root) liegt
    return render_template('Impressum.html')

# Route für Datenschutz - NICHT GESCHÜTZT
@app.route('/datenschutz')
def datenschutz():
    # Stellt die Datenschutz.html bereit, die im template_folder (root) liegt
    return render_template('Datenschutz.html')

# NEU: Route zum Servieren des Favicons
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.static_folder, 'favicon.ico')

# Feeds abrufen und hinzufügen - JETZT GESCHÜTZT
@app.route('/feeds', methods=['GET', 'POST'])
@login_required
def handle_feeds():
    if request.method == 'POST':
        data = request.json
        if not data or not 'url' in data:
            return jsonify({"error": "URL für Feed fehlt"}), 400

        feed_url = data['url']
        topic = data.get('topic', None)
        name = data.get('name', None)
        is_active = data.get('is_active', True)

        # Prüfen, ob Feed bereits existiert
        existing_feed = PodcastFeed.query.filter_by(url=feed_url).first()
        if existing_feed:
            # Wenn der Feed bereits existiert, aktualisiere Name, Thema und Aktiv-Status, falls neuere Daten vorliegen
            # Nur aktualisieren, wenn der Wert in der Importdatei vorhanden und im DB-Eintrag noch nicht gesetzt ist
            if name and not existing_feed.name:
                existing_feed.name = name
            if topic and not existing_feed.topic:
                existing_feed.topic = topic
            existing_feed.is_active = is_active # Aktiv-Status immer aktualisieren
            db.session.commit()
            return jsonify({"message": "Feed bereits vorhanden und aktualisiert", "id": existing_feed.id, "url": existing_feed.url, "name": existing_feed.name, "topic": existing_feed.topic, "is_active": existing_feed.is_active}), 200

        new_feed = PodcastFeed(url=feed_url, name=name, topic=topic, is_active=is_active)
        db.session.add(new_feed)
        try:
            db.session.commit()
            return jsonify({"message": "Feed hinzugefügt", "id": new_feed.id, "url": new_feed.url, "name": new_feed.name, "topic": new_feed.topic, "is_active": new_feed.is_active}), 201
        except Exception as e:
            db.session.rollback() # Rollback im Fehlerfall
            print(f"Fehler beim Hinzufügen des Feeds {feed_url}: {e}") # Logge den Fehler
            return jsonify({"error": f"Fehler beim Hinzufügen des Feeds: {str(e)}"}), 500
    
    else: # GET-Anfrage
        # Sortiere Feeds zuerst nach Thema, dann nach Podcast-Name
        feeds = PodcastFeed.query.order_by(
            PodcastFeed.topic.asc(), 
            PodcastFeed.name.asc()
        ).all()
        feeds_data = []
        for feed in feeds:
            feeds_data.append({
                'id': feed.id,
                'url': feed.url,
                'name': feed.name,
                'topic': feed.topic,
                'is_active': feed.is_active,
                'last_checked': feed.last_checked.isoformat() if feed.last_checked else None
            })
        return jsonify(feeds_data)

# Feed aktualisieren (PUT) - JETZT GESCHÜTZT
@app.route('/feeds/<int:feed_id>', methods=['PUT'])
@login_required
def update_feed(feed_id):
    feed = PodcastFeed.query.get_or_404(feed_id)
    data = request.json
    
    if 'url' in data:
        feed.url = data['url']
    if 'name' in data:
        feed.name = data['name']
    if 'topic' in data:
        feed.topic = data['topic']
    if 'is_active' in data:
        feed.is_active = bool(data['is_active'])
    
    try:
        db.session.commit()
        return jsonify({"message": "Feed aktualisiert", "id": feed.id, "url": feed.url, "name": feed.name, "topic": feed.topic, "is_active": feed.is_active})
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Aktualisieren des Feeds {feed_id}: {e}")
        return jsonify({"error": f"Fehler beim Aktualisieren des Feeds: {str(e)}"}), 500


# Feed löschen (DELETE) - JETZT GESCHÜTZT
@app.route('/feeds/<int:feed_id>', methods=['DELETE'])
@login_required
def delete_feed(feed_id):
    feed = PodcastFeed.query.get_or_404(feed_id)
    try:
        db.session.delete(feed)
        db.session.commit()
        return jsonify({"message": "Feed erfolgreich gelöscht"}), 204
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Löschen des Feeds {feed_id}: {e}")
        return jsonify({"error": f"Fehler beim Löschen des Feeds: {str(e)}"}), 500

# NEUER ENDPUNKT: Feeds aus XLSX importieren - JETZT GESCHÜTZT
@app.route('/import_feeds_xlsx', methods=['POST'])
@login_required
def import_feeds_xlsx():
    data = request.json
    if not data or not isinstance(data, list):
        return jsonify({"error": "Ungültiges Datenformat. Erwartet wird eine Liste von Feeds."}), 400

    imported_count = 0
    updated_count = 0
    errors = []
    
    feeds_to_refresh_ids = []

    for feed_data in data:
        feed_url = feed_data.get('url')
        feed_name = feed_data.get('name')
        feed_topic = feed_data.get('topic')
        feed_is_active = feed_data.get('is_active', True)

        if not feed_url:
            errors.append(f"Feed ohne URL übersprungen: {feed_data}")
            continue

        existing_feed = PodcastFeed.query.filter_by(url=feed_url).first()

        if existing_feed:
            # Aktualisiere Name und Thema nur, wenn sie in der XLSX-Datei vorhanden sind und im DB-Eintrag noch nicht gesetzt sind
            if feed_name and not existing_feed.name: 
                existing_feed.name = feed_name
            if feed_topic and not existing_feed.topic: 
                existing_feed.topic = feed_topic
            existing_feed.is_active = feed_is_active # Aktiv-Status immer aktualisieren
            updated_count += 1
            feeds_to_refresh_ids.append(existing_feed.id)
        else:
            new_feed = PodcastFeed(url=feed_url, name=feed_name, topic=feed_topic, is_active=feed_is_active)
            db.session.add(new_feed)
            imported_count += 1
            feeds_to_refresh_ids.append(new_feed.id)
    
    try:
        db.session.commit() # Ein einziger Commit für alle Feed-Änderungen
    except Exception as e:
        db.session.rollback()
        errors.append(f"Fehler beim Speichern der Feeds aus XLSX: {str(e)}")
        print(f"Fehler beim Speichern der Feeds aus XLSX: {e}")
        # Wenn der Commit fehlschlägt, können wir keine Episoden aktualisieren
        return jsonify({
            "message": "Fehler beim Importieren der Feeds.",
            "imported_count": imported_count,
            "updated_count": updated_count,
            "refreshed_episodes_count": 0,
            "errors": errors
        }), 500


    refreshed_episodes_count = 0
    # Aktualisiere Episoden nur für neu hinzugefügte oder aktualisierte Feeds
    for feed_id in feeds_to_refresh_ids:
        feed = PodcastFeed.query.get(feed_id)
        if feed and feed.is_active:
            episodes_data = parse_rss_feed(feed.url)
            if episodes_data:
                new_episodes_for_feed_count = 0
                for ep_data in episodes_data:
                    # Prüfe, ob die Episode bereits existiert, bevor du sie hinzufügst
                    existing_episode = Episode.query.filter_by(url=ep_data['url']).first()
                    if not existing_episode:
                        new_episode = Episode(
                            feed_id=feed.id,
                            title=ep_data['title'],
                            description=ep_data['description'],
                            pub_date=ep_data['pub_date'],
                            url=ep_data['url'],
                            is_favorite=False,
                            host=ep_data['host']
                        )
                        db.session.add(new_episode)
                        new_episodes_for_feed_count += 1
                feed.last_checked = datetime.utcnow()
                db.session.commit() # Commit nach jeder Feed-Aktualisierung
                refreshed_episodes_count += new_episodes_for_feed_count
            else:
                errors.append(f"Fehler beim Aktualisieren der Episoden für Feed {feed.url} (URL: {feed.url})")
                print(f"Fehler beim Aktualisieren der Episoden für Feed {feed.url} (URL: {feed.url})")


    return jsonify({
        "message": f"Feeds erfolgreich importiert: {imported_count} neu, {updated_count} aktualisiert. {refreshed_episodes_count} neue Episoden hinzugefügt.",
        "imported_count": imported_count,
        "updated_count": updated_count,
        "refreshed_episodes_count": refreshed_episodes_count,
        "errors": errors
    }), 200


# Episoden für einen spezifischen Feed aktualisieren - JETZT GESCHÜTZT
@app.route('/feeds/<int:feed_id>/refresh_episodes', methods=['POST'])
@login_required
def refresh_episodes_endpoint(feed_id): 
    feed = PodcastFeed.query.get(feed_id)
    if not feed:
        return jsonify({"error": "Feed nicht gefunden"}), 404
    if not feed.is_active:
        return jsonify({"message": "Feed ist inaktiv und kann nicht aktualisiert werden."}), 400

    episodes_data = parse_rss_feed(feed.url)
    if not episodes_data:
        # Hier ist es wichtig, den Fehler zu loggen, damit du ihn im Terminal siehst
        print(f"Fehler beim Parsen/Abrufen von RSS-Feed {feed.url} für Feed ID {feed_id}")
        return jsonify({"message": "Keine Episoden gefunden oder Fehler beim Parsen des Feeds"}), 500

    new_episodes_count = 0
    for ep_data in episodes_data:
        existing_episode = Episode.query.filter_by(url=ep_data['url']).first()
        if not existing_episode:
            new_episode = Episode(
                feed_id=feed.id,
                title=ep_data['title'],
                description=ep_data['description'],
                pub_date=ep_data['pub_date'],
                url=ep_data['url'],
                is_favorite=False,
                host=ep_data['host']
            )
            db.session.add(new_episode)
            new_episodes_count += 1
    
    feed.last_checked = datetime.utcnow()
    try:
        db.session.commit()
        return jsonify({"message": f"Episoden für Feed aktualisiert. {new_episodes_count} neue Episoden hinzugefügt."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Speichern der aktualisierten Episoden für Feed {feed_id}: {e}")
        return jsonify({"error": f"Fehler beim Speichern der Episoden: {str(e)}"}), 500


# Alle Episoden abrufen - JETZT GESCHÜTZT
@app.route('/episodes', methods=['GET'])
@login_required
def get_episodes():
    episodes = Episode.query.all()
    episodes_data = []
    for ep in episodes:
        episodes_data.append({
            'id': ep.id,
            'feed_id': ep.feed_id,
            'title': ep.title,
            'description': ep.description,
            'pub_date': ep.pub_date.isoformat() if ep.pub_date else None,
            'url': ep.url,
            'is_favorite': ep.is_favorite,
            'host': ep.host
        })
    return jsonify(episodes_data)

# Episode aktualisieren (PUT) - JETZT GESCHÜTZT
@app.route('/episodes/<int:episode_id>', methods=['PUT'])
@login_required
def update_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    data = request.json
    
    if 'title' in data:
        episode.title = data['title']
    if 'description' in data:
        episode.description = data['description']
    if 'pub_date' in data:
        try:
            episode.pub_date = datetime.fromisoformat(data['pub_date'])
        except ValueError:
            return jsonify({"error": "Ungültiges Datumsformat für pub_date"}), 400
    if 'url' in data:
        episode.url = data['url']
    if 'is_favorite' in data:
        episode.is_favorite = bool(data['is_favorite'])
    if 'host' in data:
        episode.host = data['host']
        
    try:
        db.session.commit()
        return jsonify({"message": "Episode aktualisiert", "id": episode.id, "title": episode.title, "is_favorite": episode.is_favorite, "host": episode.host})
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Aktualisieren der Episode {episode_id}: {e}")
        return jsonify({"error": f"Fehler beim Aktualisieren der Episode: {str(e)}"}), 500

# Episode löschen (DELETE) - JETZT GESCHÜTZT
@app.route('/episodes/<int:episode_id>', methods=['DELETE'])
@login_required
def delete_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    try:
        db.session.delete(episode)
        db.session.commit()
        return jsonify({"message": "Episode erfolgreich gelöscht"}), 204
    except Exception as e:
        db.session.rollback()
        print(f"Fehler beim Löschen der Episode {episode_id}: {e}")
        return jsonify({"error": f"Fehler beim Löschen der Episode: {str(e)}"}), 500


if __name__ == '__main__':
    with app.app_context():
        # Dies erstellt die Datenbanktabellen, falls sie noch nicht existieren.
        # WICHTIG: Bei Änderungen am Datenmodell und wenn du eine leere DB willst,
        # musst du die 'podcast_tracker.db' Datei MANUELL LÖSCHEN, bevor du die App startest.
        # Beispiel: rm podcast_tracker.db
        db.create_all()
    app.run(debug=True, host='0.0.0.0')

