import os
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime
import requests
import xml.etree.ElementTree as ET

# Lade Umgebungsvariablen aus .env-Datei (für lokale Entwicklung, in Codespaces durch Secrets überschrieben)
load_dotenv()

# Setze den static_folder explizit auf den absoluten Pfad des aktuellen Verzeichnisses
app = Flask(__name__, static_folder=os.path.abspath(os.path.dirname(__file__)))

# CORS für alle Routen aktivieren (für Entwicklung).
# In einer Produktionsumgebung sollte dies auf spezifische Ursprünge beschränkt werden.
CORS(app)

# Konfiguration der Datenbank
# Die DATABASE_URL wird aus den Umgebungsvariablen geladen (z.B. GitHub Codespaces Secret)
# Fallback auf SQLite für den Fall, dass DATABASE_URL nicht gesetzt ist (z.B. erster lokaler Test)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'podcast_tracker.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Deaktiviert Warnungen zur Änderungsverfolgung

db = SQLAlchemy(app)

# Definition des Datenmodells für Podcast-Feeds
class PodcastFeed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Die URL des RSS-Feeds, muss einzigartig sein und darf nicht leer sein
    url = db.Column(db.String(500), unique=True, nullable=False)
    # Optionales Thema des Podcasts
    topic = db.Column(db.String(255))
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
    # Neues Feld für den Favoritenstatus
    is_favorite = db.Column(db.Boolean, default=False)

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
                    'url': episode_url
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

# API-Endpunkte

# Route zum Servieren der HTML-Datei (Frontend)
@app.route('/')
def serve_frontend():
    # Stellt die podcast_tracker-DB.html bereit, indem der static_folder verwendet wird
    return send_from_directory(app.static_folder, 'podcast_tracker-DB.html')

# Feeds abrufen und hinzufügen
@app.route('/feeds', methods=['GET', 'POST'])
def handle_feeds():
    if request.method == 'POST':
        data = request.json
        if not data or not 'url' in data:
            return jsonify({"error": "URL für Feed fehlt"}), 400

        feed_url = data['url']
        topic = data.get('topic', None)

        # Prüfen, ob Feed bereits existiert
        existing_feed = PodcastFeed.query.filter_by(url=feed_url).first()
        if existing_feed:
            return jsonify({"message": "Feed bereits vorhanden", "id": existing_feed.id, "url": existing_feed.url, "topic": existing_feed.topic}), 200

        new_feed = PodcastFeed(url=feed_url, topic=topic)
        db.session.add(new_feed)
        db.session.commit()
        return jsonify({"message": "Feed hinzugefügt", "id": new_feed.id, "url": new_feed.url, "topic": new_feed.topic}), 201
    
    else: # GET-Anfrage
        feeds = PodcastFeed.query.all()
        feeds_data = []
        for feed in feeds:
            feeds_data.append({
                'id': feed.id,
                'url': feed.url,
                'topic': feed.topic,
                'last_checked': feed.last_checked.isoformat() if feed.last_checked else None
            })
        return jsonify(feeds_data)

# Feed aktualisieren (PUT)
@app.route('/feeds/<int:feed_id>', methods=['PUT'])
def update_feed(feed_id):
    feed = PodcastFeed.query.get_or_404(feed_id)
    data = request.json
    
    if 'url' in data:
        feed.url = data['url']
    if 'topic' in data:
        feed.topic = data['topic']
    
    db.session.commit()
    return jsonify({"message": "Feed aktualisiert", "id": feed.id, "url": feed.url, "topic": feed.topic})

# Feed löschen (DELETE)
@app.route('/feeds/<int:feed_id>', methods=['DELETE'])
def delete_feed(feed_id):
    feed = PodcastFeed.query.get_or_404(feed_id)
    db.session.delete(feed)
    db.session.commit()
    return jsonify({"message": "Feed erfolgreich gelöscht"}), 204

# Episoden für einen spezifischen Feed aktualisieren
@app.route('/feeds/<int:feed_id>/refresh_episodes', methods=['POST'])
def refresh_episodes(feed_id):
    feed = PodcastFeed.query.get(feed_id)
    if not feed:
        return jsonify({"error": "Feed nicht gefunden"}), 404

    episodes_data = parse_rss_feed(feed.url)
    if not episodes_data:
        return jsonify({"message": "Keine Episoden gefunden oder Fehler beim Parsen des Feeds"}), 500

    new_episodes_count = 0
    for ep_data in episodes_data:
        # Prüfen, ob Episode bereits existiert (anhand der URL)
        existing_episode = Episode.query.filter_by(url=ep_data['url']).first()
        if not existing_episode:
            new_episode = Episode(
                feed_id=feed.id,
                title=ep_data['title'],
                description=ep_data['description'],
                pub_date=ep_data['pub_date'],
                url=ep_data['url'],
                is_favorite=False # Standardmäßig nicht favorisiert
            )
            db.session.add(new_episode)
            new_episodes_count += 1
    
    feed.last_checked = datetime.utcnow() # Aktualisiere den Zeitpunkt der letzten Prüfung
    db.session.commit()
    return jsonify({"message": f"Episoden für Feed aktualisiert. {new_episodes_count} neue Episoden hinzugefügt."}), 200

# Alle Episoden abrufen
@app.route('/episodes', methods=['GET'])
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
            'is_favorite': ep.is_favorite # Favoritenstatus hinzufügen
        })
    return jsonify(episodes_data)

# Episode aktualisieren (PUT)
@app.route('/episodes/<int:episode_id>', methods=['PUT'])
def update_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    data = request.json
    
    if 'title' in data:
        episode.title = data['title']
    if 'description' in data:
        episode.description = data['description']
    if 'pub_date' in data:
        # Versuche, das Datum zu parsen, wenn es als String kommt
        try:
            episode.pub_date = datetime.fromisoformat(data['pub_date'])
        except ValueError:
            return jsonify({"error": "Ungültiges Datumsformat für pub_date"}), 400
    if 'url' in data:
        episode.url = data['url']
    if 'is_favorite' in data: # Favoritenstatus aktualisieren
        episode.is_favorite = bool(data['is_favorite'])
        
    db.session.commit()
    return jsonify({"message": "Episode aktualisiert", "id": episode.id, "title": episode.title, "is_favorite": episode.is_favorite})

# Episode löschen (DELETE)
@app.route('/episodes/<int:episode_id>', methods=['DELETE'])
def delete_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    db.session.delete(episode)
    db.session.commit()
    return jsonify({"message": "Episode erfolgreich gelöscht"}), 204


if __name__ == '__main__':
    # Stellt sicher, dass die Datenbanktabellen existieren, wenn die App läuft.
    # Dies wird nur ausgeführt, wenn die Datei direkt als Hauptprogramm gestartet wird.
    with app.app_context():
        db.create_all() # Erstellt Tabellen, falls sie noch nicht existieren
    
    # Startet den Flask-Entwicklungsserver
    # debug=True ermöglicht automatischen Neuladen bei Codeänderungen und detailliertere Fehlermeldungen
    # host='0.0.0.0' ist notwendig, damit die App in Codespaces von außen erreichbar ist
    app.run(debug=True, host='0.0.0.0')
