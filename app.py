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
        name = data.get('name', None)
        is_active = data.get('is_active', True)

        # Prüfen, ob Feed bereits existiert
        existing_feed = PodcastFeed.query.filter_by(url=feed_url).first()
        if existing_feed:
            # Wenn der Feed bereits existiert, aktualisiere Name, Thema und Aktiv-Status, falls neuere Daten vorliegen
            if name and not existing_feed.name:
                existing_feed.name = name
            if topic and not existing_feed.topic:
                existing_feed.topic = topic
            existing_feed.is_active = is_active
            db.session.commit()
            return jsonify({"message": "Feed bereits vorhanden", "id": existing_feed.id, "url": existing_feed.url, "name": existing_feed.name, "topic": existing_feed.topic, "is_active": existing_feed.is_active}), 200

        new_feed = PodcastFeed(url=feed_url, name=name, topic=topic, is_active=is_active)
        db.session.add(new_feed)
        db.session.commit()
        return jsonify({"message": "Feed hinzugefügt", "id": new_feed.id, "url": new_feed.url, "name": new_feed.name, "topic": new_feed.topic, "is_active": new_feed.is_active}), 201
    
    else: # GET-Anfrage
        feeds = PodcastFeed.query.all()
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

# Feed aktualisieren (PUT)
@app.route('/feeds/<int:feed_id>', methods=['PUT'])
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
    
    db.session.commit()
    return jsonify({"message": "Feed aktualisiert", "id": feed.id, "url": feed.url, "name": feed.name, "topic": feed.topic, "is_active": feed.is_active})

# Feed löschen (DELETE)
@app.route('/feeds/<int:feed_id>', methods=['DELETE'])
def delete_feed(feed_id):
    feed = PodcastFeed.query.get_or_404(feed_id)
    db.session.delete(feed)
    db.session.commit()
    return jsonify({"message": "Feed erfolgreich gelöscht"}), 204

# NEUER ENDPUNKT: Feeds aus XLSX importieren
@app.route('/import_feeds_xlsx', methods=['POST'])
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
            if feed_name and not existing_feed.name: 
                existing_feed.name = feed_name
            if feed_topic and not existing_feed.topic: 
                existing_feed.topic = feed_topic
            existing_feed.is_active = feed_is_active
            db.session.commit()
            updated_count += 1
            feeds_to_refresh_ids.append(existing_feed.id)
        else:
            new_feed = PodcastFeed(url=feed_url, name=feed_name, topic=feed_topic, is_active=feed_is_active)
            db.session.add(new_feed)
            try:
                db.session.commit()
                imported_count += 1
                feeds_to_refresh_ids.append(new_feed.id)
            except Exception as e:
                db.session.rollback() 
                errors.append(f"Fehler beim Hinzufügen von Feed {feed_url}: {str(e)}")
                print(f"Fehler beim Hinzufügen von Feed {feed_url}: {str(e)}")


    refreshed_episodes_count = 0
    for feed_id in feeds_to_refresh_ids:
        feed = PodcastFeed.query.get(feed_id)
        if feed and feed.is_active:
            episodes_data = parse_rss_feed(feed.url)
            if episodes_data:
                new_episodes_for_feed_count = 0
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
                        new_episodes_for_feed_count += 1
                feed.last_checked = datetime.utcnow()
                db.session.commit()
                refreshed_episodes_count += new_episodes_for_feed_count
            else:
                errors.append(f"Fehler beim Aktualisieren der Episoden für Feed {feed.url}")

    return jsonify({
        "message": f"Feeds erfolgreich importiert: {imported_count} neu, {updated_count} aktualisiert. {refreshed_episodes_count} neue Episoden hinzugefügt.",
        "imported_count": imported_count,
        "updated_count": updated_count,
        "refreshed_episodes_count": refreshed_episodes_count,
        "errors": errors
    }), 200


# Episoden für einen spezifischen Feed aktualisieren
@app.route('/feeds/<int:feed_id>/refresh_episodes', methods=['POST'])
def refresh_episodes_endpoint(feed_id): 
    feed = PodcastFeed.query.get(feed_id)
    if not feed:
        return jsonify({"error": "Feed nicht gefunden"}), 404
    if not feed.is_active:
        return jsonify({"message": "Feed ist inaktiv und kann nicht aktualisiert werden."}), 400

    episodes_data = parse_rss_feed(feed.url)
    if not episodes_data:
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
            'is_favorite': ep.is_favorite,
            'host': ep.host
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
        
    db.session.commit()
    return jsonify({"message": "Episode aktualisiert", "id": episode.id, "title": episode.title, "is_favorite": episode.is_favorite, "host": episode.host})

# Episode löschen (DELETE)
@app.route('/episodes/<int:episode_id>', methods=['DELETE'])
def delete_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    db.session.delete(episode)
    db.session.commit()
    return jsonify({"message": "Episode erfolgreich gelöscht"}), 204

# Route zum Servieren der Impressum-HTML-Datei
@app.route('/impressum')
def serve_impressum():
    # Stellt die Impressum.html bereit, indem der static_folder verwendet wird
    return send_from_directory(app.static_folder, 'Impressum.html')

# Route zum Servieren der Datenschutz-HTML-Datei
@app.route('/datenschutz')
def serve_datenschutz():
    return send_from_directory(app.static_folder, 'Datenschutz.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0')
