import os
from flask import Flask, request, jsonify, render_template, send_from_directory, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime, timedelta
import requests
import xml.etree.ElementTree as ET
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Lade Umgebungsvariablen aus .env-Datei (für lokale Entwicklung, in Codespaces durch Secrets überschrieben)
load_dotenv()

# Flask-Anwendung initialisieren
# 'static_folder' verweist auf den Ordner für statische Dateien (CSS, JS, Bilder, Favicon)
# 'template_folder' verweist auf den Ordner für HTML-Templates (hier das Hauptverzeichnis '.')
app = Flask(__name__, static_folder='static', template_folder='.')

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY_FLASK_LOGIN', 'your_super_secret_key_that_you_must_change_in_production')
# Korrektur: basedir definieren
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'podcast_tracker.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Deaktiviert Warnungen zur Objektmodifikation


db = SQLAlchemy(app)
CORS(app) # Ermöglicht Cross-Origin Requests

# Flask-Login initialisieren
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Name der Login-Route

# Dummy User-Klasse für Flask-Login
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # KORREKTUR HIER: LÄNGE DES password_hash FELDES ERHÖHT
    password_hash = db.Column(db.String(255), nullable=False) # Erhöht von 120 auf 255

    # Diese Methode wird nicht mehr für den Standardbenutzer verwendet, kann aber für andere Registrierungen nützlich sein
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    # Lade den Benutzer anhand der ID aus der Datenbank
    return User.query.get(int(user_id))

# Erstelle einen Standardbenutzer, falls keiner existiert (NUR FÜR ENTWICKLUNG/TESTZWECKE)
@app.before_request
def create_default_user():
    with app.app_context():
        if User.query.filter_by(username='user1').first() is None:
            user = User(username='user1')
            # Hier wird DEIN zuvor definierter, gehashter Passwortwert zugewiesen
            # Dieser Hash stammt von "SpeilPW"
            user.password_hash = """scrypt:32768:8:1$anilOJC7MTH87cwT$624d07e2737d25657bff2e6d516bd38cdee48729cd9421b22b8f6a30f3e49a3627e3a334718f84216a6698bf0c55a21043f63fe4c73c9007ae212d6d657929d3""" 
            db.session.add(user)
            db.session.commit()
            print("Default user 'user1' created with predefined hash.")


# Datenbankmodelle
class PodcastFeed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    topic = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    last_checked = db.Column(db.DateTime, default=datetime.now)
    homepage_url = db.Column(db.String(500)) # Neues Feld für Homepage URL

    episodes = db.relationship('Episode', backref='feed', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<PodcastFeed {self.name}>'

class Episode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    feed_id = db.Column(db.Integer, db.ForeignKey('podcast_feed.id'), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    pub_date = db.Column(db.DateTime, nullable=False)
    url = db.Column(db.String(500))
    is_favorite = db.Column(db.Boolean, default=False)
    host = db.Column(db.String(255))

    def __repr__(self):
        return f'<Episode {self.title}>'

# Hilfsfunktion zum Parsen von Datumsstrings
def parse_date(date_string):
    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",  # RFC 2822 (most common for RSS)
        "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822 with UTC offset
        "%Y-%m-%dT%H:%M:%S%Z",      # ISO 8601 (often for Atom feeds)
        "%Y-%m-%dT%H:%M:%S.%fZ",    # ISO 8601 with milliseconds and 'Z' for UTC
        "%Y-%m-%d %H:%M:%S",        # Common SQL format
        "%a, %d %b %Y %H:%M:%S %z", # Sometimes timezone is like -0000
        "%a, %d %b %Y %H:%M:%S GMT", # Specific GMT
        "%Y-%m-%dT%H:%M:%S",        # ISO 8601 without timezone
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    print(f"Warnung: Datum '{date_string}' konnte nicht geparst werden.")
    return datetime.now() # Fallback auf aktuelle Zeit, wenn Parsen fehlschlägt

def parse_rss_feed(feed_url):
    """
    Parst einen RSS- oder Atom-Feed und gibt Feed- und Episodendaten zurück.
    """
    try:
        response = requests.get(feed_url, timeout=10) # Timeout hinzugefügt
        response.raise_for_status() # Löst HTTPError für schlechte Antworten (4xx oder 5xx) aus
        
        # Versuche, den XML-Baum zu parsen
        root = ET.fromstring(response.content)
        
        # Namespaces für RSS, iTunes und Atom
        namespaces = {
            'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd', 
            'googleplay': 'http://www.google.com/schemas/play-podcasts/1.0',
            'atom': 'http://www.w3.org/2005/Atom',
            'dc': 'http://purl.org/dc/elements/1.1/' # Hinzugefügt für Dublin Core Creator
        }

        feed_data = {}
        episodes = []

        # Prüfen, ob es sich um einen RSS-Feed handelt (hat ein 'channel'-Element)
        if root.find('channel') is not None:
            channel = root.find('channel')
            # RSS Feed Parsing
            feed_data['name'] = channel.find('title').text if channel.find('title') is not None else 'Unbekannter Podcast'
            
            # Homepage URL: Priorisiere itunes:new-feed-url, dann atom:link rel="alternate", dann channel/link
            homepage_url = None
            itunes_link = channel.find('itunes:new-feed-url', namespaces)
            if itunes_link is not None and itunes_link.text:
                homepage_url = itunes_link.text
            else:
                atom_link = channel.find('atom:link[@rel="alternate"]', namespaces)
                if atom_link is not None and 'href' in atom_link.attrib:
                    homepage_url = atom_link.attrib['href']
                else:
                    link = channel.find('link')
                    if link is not None:
                        # Einige Feeds haben Link als Attribut, andere als Text
                        homepage_url = link.text if link.text else link.attrib.get('href')

            # Validiere die homepage_url
            if homepage_url and not (homepage_url.startswith('http://') or homepage_url.startswith('https://')):
                homepage_url = None # Setze ungültige URLs auf None
            feed_data['homepage_url'] = homepage_url

            # Den Topic aus verschiedenen möglichen Tags lesen
            topic = None
            category_elem = channel.find('category')
            if category_elem is not None and category_elem.text:
                topic = category_elem.text
            else:
                itunes_category_elem = channel.find('itunes:category', namespaces)
                if itunes_category_elem is not None:
                    topic = itunes_category_elem.attrib.get('text')
            feed_data['topic'] = topic

            for item in channel.findall('item'):
                title_elem = item.find('title')
                description_elem = item.find('description')
                pub_date_elem = item.find('pubDate')
                url_elem = item.find('enclosure') # enclosure-Tag für die Mediendatei-URL
                
                # Alternative: direkter Link aus dem item
                if url_elem is None:
                    url_elem = item.find('link') 

                # KORREKTUR: Host/Author Parsing verbessert
                host_text = 'Unbekannter Host' # Default value
                
                # Priority 1: item-level iTunes author
                itunes_author_item = item.find('itunes:author', namespaces)
                if itunes_author_item is not None and itunes_author_item.text:
                    host_text = itunes_author_item.text.strip()
                else:
                    # Priority 2: item-level generic author
                    author_item = item.find('author')
                    if author_item is not None:
                        # Some <author> tags might contain <name> sub-element
                        name_in_author = author_item.find('name')
                        if name_in_author is not None and name_in_author.text:
                            host_text = name_in_author.text.strip()
                        elif author_item.text: # Direct text in <author> tag
                            host_text = author_item.text.strip()
                    else:
                        # Priority 3: item-level Dublin Core creator
                        dc_creator_item = item.find('dc:creator', namespaces)
                        if dc_creator_item is not None and dc_creator_item.text:
                            host_text = dc_creator_item.text.strip()
                        else:
                            # Priority 4: channel-level iTunes owner/author (common for entire podcast)
                            itunes_owner_name = channel.find('itunes:owner/itunes:name', namespaces)
                            if itunes_owner_name is not None and itunes_owner_name.text:
                                host_text = itunes_owner_name.text.strip()
                            else:
                                itunes_author_channel = channel.find('itunes:author', namespaces)
                                if itunes_author_channel is not None and itunes_author_channel.text:
                                    host_text = itunes_author_channel.text.strip()
                                else:
                                    # Priority 5: channel-level generic author
                                    author_channel = channel.find('author')
                                    if author_channel is not None and author_channel.text:
                                        host_text = author_channel.text.strip()

                
                episode_url = None
                if url_elem is not None:
                    if 'url' in url_elem.attrib: # Für <enclosure url="...">
                        episode_url = url_elem.attrib['url']
                    elif url_elem.text and (url_elem.text.startswith('http://') or url_elem.text.startswith('https://')): # Für <link>text</link>
                        episode_url = url_elem.text # Korrigiert: url_elem.text statt url.text

                # Überprüfe, ob episode_url ein valider Link ist (kann auch nur ein HTML-Link sein)
                if episode_url and not (episode_url.startswith('http://') or episode_url.startswith('https://')):
                    episode_url = None # Setze ungültige URLs auf None

                episodes.append({
                    'title': title_elem.text if title_elem is not None else 'Unbekannter Titel',
                    'description': description_elem.text if description_elem is not None else '',
                    'pub_date': parse_date(pub_date_elem.text) if pub_date_elem is not None else datetime.now(),
                    'url': episode_url,
                    'host': host_text # Use the determined host_text
                })
        
        # Prüfen, ob es sich um einen Atom-Feed handelt (hat ein 'feed'-Element als root)
        elif root.tag == '{http://www.w3.org/2005/Atom}feed':
            # Atom Feed
            feed_data['name'] = root.find('{http://www.w3.org/2005/Atom}title', namespaces).text if root.find('{http://www.w3.org/2005/Atom}title', namespaces) is not None else 'Unbekannter Atom Feed'
            feed_data['homepage_url'] = root.find('{http://www.w3.org/2005/Atom}link[@rel="alternate"]', namespaces).attrib['href'] if root.find('{http://www.w3.org/2005/Atom}link[@rel="alternate"]', namespaces) is not None else None
            feed_data['topic'] = None # Atom hat kein direktes "topic" Feld

            for item in root.findall('{http://www.w3.org/2005/Atom}entry', namespaces):
                title_elem = item.find('{http://www.w3.org/2005/Atom}title', namespaces)
                description_elem = item.find('{http://www.w3.org/2005/Atom}summary', namespaces) or item.find('{http://www.w3.org/2005/Atom}content', namespaces)
                pub_date_elem = item.find('{http://www.w3.org/2005/Atom}published', namespaces)
                url_elem = item.find('{http://www.w3.org/2005/Atom}link[@rel="enclosure"]', namespaces) or item.find('{http://www.w3.org/2005/Atom}link', namespaces)
                
                # KORREKTUR: Host/Author Parsing verbessert für Atom
                host_text = 'Unbekannter Host'
                author_elem = item.find('{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name', namespaces)
                if author_elem is not None and author_elem.text:
                    host_text = author_elem.text.strip()
                else:
                    channel_author_elem = root.find('{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name', namespaces)
                    if channel_author_elem is not None and channel_author_elem.text:
                        host_text = channel_author_elem.text.strip()


                episode_url = url_elem.attrib['href'] if url_elem is not None and 'href' in url_elem.attrib else None
                
                if episode_url and not (episode_url.startswith('http://') or episode_url.startswith('https://')):
                    episode_url = None # Setze ungültige URLs auf None

                episodes.append({
                    'title': title_elem.text if title_elem is not None else 'Unbekannter Titel',
                    'description': description_elem.text if description_elem is not None else '',
                    'pub_date': parse_date(pub_date_elem.text) if pub_date_elem is not None else datetime.now(),
                    'url': episode_url,
                    'host': host_text
                })
        else:
            raise ValueError("Ungültiges Feed-Format: Weder RSS-Channel noch Atom-Feed gefunden.")

        return feed_data, episodes

    except requests.exceptions.RequestException as e:
        print(f"Netzwerkfehler beim Abrufen des RSS-Feeds {feed_url}: {e}")
        return None, None
    except ET.ParseError as e:
        print(f"Fehler beim Parsen des RSS-Feeds {feed_url}: {e}")
        return None, None
    except Exception as e:
        print(f"Ein unerwarteter Fehler ist aufgetreten beim Parsen von {feed_url}: {e}")
        return None, None


# Routen
@app.route('/')
@login_required
def index():
    return render_template('podcast_tracker-DB.html', username=current_user.username)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Erfolgreich eingeloggt!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Ungültiger Benutzername oder Passwort.', 'danger')
    return render_template('login.html') # Du musst eine login.html Datei erstellen

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sie wurden erfolgreich abgemeldet.', 'info')
    return redirect(url_for('login'))

# Favicon-Route
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'PTr-favicon.ico', mimetype='image/vnd.microsoft.icon')

# API-Endpunkte
@app.route('/feeds', methods=['GET'])
@login_required
def get_feeds():
    feeds = PodcastFeed.query.all()
    # Füge die Anzahl der Episoden pro Feed hinzu
    feeds_data = []
    for feed in feeds:
        episodes_count = Episode.query.filter_by(feed_id=feed.id).count()
        feeds_data.append({
            'id': feed.id,
            'url': feed.url,
            'name': feed.name,
            'topic': feed.topic,
            'is_active': feed.is_active,
            'last_checked': feed.last_checked.isoformat(),
            'homepage_url': feed.homepage_url,
            'episodes_count': episodes_count
        })
    return jsonify(feeds_data)

@app.route('/episodes', methods=['GET'])
@login_required
def get_episodes():
    episodes = db.session.query(Episode, PodcastFeed.name.label('podcast_name')).join(PodcastFeed).all()
    episodes_data = [{
        'id': ep.Episode.id,
        'feed_id': ep.Episode.feed_id,
        'title': ep.Episode.title,
        'description': ep.Episode.description,
        'pub_date': ep.Episode.pub_date.isoformat(),
        'url': ep.Episode.url,
        'is_favorite': ep.Episode.is_favorite,
        'host': ep.Episode.host,
        'podcast_name': ep.podcast_name # Füge den Podcast-Namen hinzu
    } for ep in episodes]
    return jsonify(episodes_data)

@app.route('/add_feed', methods=['POST'])
@login_required
def add_feed():
    data = request.json
    feed_url = data.get('feed_url')

    if not feed_url:
        return jsonify({"error": "RSS Feed URL ist erforderlich."}), 400

    # Prüfen, ob der Feed bereits existiert
    existing_feed = PodcastFeed.query.filter_by(url=feed_url).first()
    if existing_feed:
        # Wenn der Feed existiert, aktualisiere ihn stattdessen
        feed_data, episodes_data = parse_rss_feed(feed_url)
        if feed_data:
            try:
                # KORREKTUR: Name und Topic nur aktualisieren, wenn sie nicht bereits manuell gesetzt wurden
                if existing_feed.name == existing_feed.url or existing_feed.name == 'Unbekannter Podcast':
                    existing_feed.name = feed_data.get('name', existing_feed.name)
                
                # Wenn das geparste Thema nicht None ist UND das aktuelle Thema leer ist ODER es gleich dem geparsten ist
                if feed_data.get('topic') is not None and (existing_feed.topic is None or existing_feed.topic == feed_data['topic']):
                    existing_feed.topic = feed_data['topic']

                existing_feed.homepage_url = feed_data.get('homepage_url', existing_feed.homepage_url)
                existing_feed.last_checked = datetime.now()
                db.session.commit()

                # Bestehende Episoden für diesen Feed löschen, um Duplikate zu vermeiden
                Episode.query.filter_by(feed_id=existing_feed.id).delete()
                db.session.commit() # Commit, um Löschung zu persistieren

                # Neue Episoden hinzufügen
                for ep_data in episodes_data:
                    ep_data['feed_id'] = existing_feed.id 
                    ep_data.setdefault('is_favorite', False)
                    episode = Episode(**ep_data)
                    db.session.add(episode)
                
                db.session.commit()
                
                flash(f"Feed '{existing_feed.name}' und Episoden erfolgreich aktualisiert (existierte bereits)!", "success")
                return jsonify({"message": f"Feed '{existing_feed.name}' und Episoden erfolgreich aktualisiert (existierte bereits)!"}), 200
            except Exception as e:
                db.session.rollback()
                flash(f"Fehler beim Aktualisieren des Feeds: {str(e)}", "danger")
                return jsonify({"error": f"Fehler beim Aktualisieren des Feeds: {str(e)}"}), 500
        else:
            flash("Fehler beim Parsen des bestehenden RSS-Feeds oder ungültige URL.", "danger")
            return jsonify({"error": "Fehler beim Parsen des bestehenden RSS-Feeds oder ungültige URL."}), 400

    feed_data, episodes_data = parse_rss_feed(feed_url)

    if feed_data:
        try:
            new_feed = PodcastFeed(
                url=feed_url,
                name=feed_data.get('name', 'Unbekannter Podcast'),
                topic=feed_data.get('topic'),
                is_active=True,
                last_checked=datetime.now(),
                homepage_url=feed_data.get('homepage_url')
            )
            db.session.add(new_feed)
            db.session.commit()

            for ep_data in episodes_data:
                ep_data['feed_id'] = new_feed.id 
                ep_data.setdefault('is_favorite', False)
                episode = Episode(**ep_data)
                db.session.add(episode)
            
            db.session.commit()
            
            flash(f"Feed '{new_feed.name}' und Episoden erfolgreich hinzugefügt!", "success")
            return jsonify({"message": f"Feed '{new_feed.name}' und Episoden erfolgreich hinzugefügt!"}), 201
        except Exception as e:
            db.session.rollback()
            flash(f"Fehler beim Hinzufügen des Feeds: {str(e)}", "danger")
            return jsonify({"error": f"Fehler beim Hinzufügen des Feeds: {str(e)}"}), 500
    else:
        flash("Fehler beim Parsen des RSS-Feeds oder ungültige URL.", "danger")
        return jsonify({"error": "Fehler beim Parsen des RSS-Feeds oder ungültige URL."}), 400

# Route für die Aktualisierung eines Feeds (wird von "Alle Aktualisieren" im Frontend aufgerufen)
@app.route('/feeds/<int:feed_id>/refresh_episodes', methods=['POST'])
@login_required
def refresh_episodes_endpoint(feed_id): # Umbenannt von update_feed zur besseren Unterscheidung
    feed = PodcastFeed.query.get_or_404(feed_id)
    feed_url = feed.url

    parsed_feed_data, episodes_data = parse_rss_feed(feed_url)

    if parsed_feed_data:
        try:
            # KORREKTUR: Name und Topic nur aktualisieren, wenn sie nicht bereits manuell gesetzt wurden
            # Dies verhindert das Überschreiben manueller Edits durch den RSS-Feed
            if feed.name == feed.url or feed.name == 'Unbekannter Podcast':
                 feed.name = parsed_feed_data.get('name', feed.name)
            
            if parsed_feed_data.get('topic') is not None and (feed.topic is None or feed.topic == parsed_feed_data['topic']):
                 feed.topic = parsed_feed_data['topic']

            feed.homepage_url = parsed_feed_data.get('homepage_url', feed.homepage_url)
            feed.last_checked = datetime.now()
            db.session.commit()

            # Alle alten Episoden löschen und neue hinzufügen, um Duplikate zu vermeiden und Aktualität zu gewährleisten
            Episode.query.filter_by(feed_id=feed.id).delete()
            db.session.commit()

            new_episodes_count = 0
            for ep_data in episodes_data:
                ep_data['feed_id'] = feed.id
                ep_data.setdefault('is_favorite', False)
                
                # DEBUGGING PRINT: Überprüfen, ob Host vorhanden ist, bevor er hinzugefügt wird
                print(f"DEBUG: Preparing episode '{ep_data.get('title', 'N/A')}', Host: '{ep_data.get('host', 'N/A')}' for feed ID {feed.id}")
                
                episode = Episode(**ep_data)
                db.session.add(episode)
                new_episodes_count += 1
            
            db.session.commit()
            print(f"DEBUG: Committed {new_episodes_count} new episodes for feed {feed.id}. Host values should be saved.") # DEBUG Print
            flash(f"Feed '{feed.name}' und Episoden erfolgreich aktualisiert!", "success")
            return jsonify({"message": f"Feed '{feed.name}' und Episoden erfolgreich aktualisiert!"}), 200
        except Exception as e:
            db.session.rollback()
            print(f"ERROR: Failed to update feed {feed.id} - {str(e)}") # DEBUG Print for exceptions
            flash(f"Fehler beim Aktualisieren des Feeds: {str(e)}", "danger")
            return jsonify({"error": f"Fehler beim Aktualisieren des Feeds: {str(e)}"}), 500
    else:
        print(f"ERROR: Failed to parse RSS feed {feed_url} during refresh.") # DEBUG Print for parsing failure
        flash("Fehler beim Parsen des RSS-Feeds während der Aktualisierung.", "danger")
        return jsonify({"error": "Fehler beim Parsen des RSS-Feeds während der Aktualisierung."}), 400

# Route für das Aktualisieren von Feed-Metadaten (z.B. Topic, is_active) durch das Frontend
@app.route('/feeds/<int:feed_id>', methods=['PUT'])
@login_required
def update_feed_metadata(feed_id): # Umbenannt zur besseren Unterscheidung
    feed = PodcastFeed.query.get_or_404(feed_id)
    data = request.json
    
    try:
        if 'url' in data: # Normalerweise nicht über PUT geändert
            feed.url = data['url']
        if 'name' in data: # Wird direkt vom Frontend geändert
            feed.name = data['name']
        if 'topic' in data: # Wird direkt vom Frontend geändert
            feed.topic = data['topic']
        if 'is_active' in data:
            feed.is_active = bool(data['is_active'])
        if 'homepage_url' in data: # Normalerweise nicht über PUT geändert
            feed.homepage_url = data['homepage_url']
        
        db.session.commit()
        flash("Feed aktualisiert", "success")
        return jsonify({"message": "Feed aktualisiert", "id": feed.id, "url": feed.url, "name": feed.name, "topic": feed.topic, "is_active": feed.is_active, "homepage_url": feed.homepage_url}), 200
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Aktualisieren des Feeds: {str(e)}", "danger")
        return jsonify({"error": f"Fehler beim Aktualisieren des Feeds: {str(e)}"}), 500


@app.route('/delete_feed/<int:feed_id>', methods=['DELETE'])
@login_required
def delete_feed(feed_id):
    feed = PodcastFeed.query.get_or_404(feed_id)
    try:
        db.session.delete(feed)
        db.session.commit()
        flash("Feed erfolgreich gelöscht", "success")
        return jsonify({"message": "Feed erfolgreich gelöscht"}), 204
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Löschen des Feeds: {str(e)}", "danger")
        return jsonify({"error": f"Fehler beim Löschen des Feeds: {str(e)}"}), 500

@app.route('/episodes/<int:episode_id>', methods=['PUT']) # Vereinfacht von update_episode
@login_required
def update_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    data = request.json
    
    # Aktualisiere nur die erlaubten Felder
    if 'title' in data:
        episode.title = data['title']
    if 'description' in data:
        episode.description = data['description']
    if 'pub_date' in data:
        episode.pub_date = parse_date(data['pub_date'])
    if 'url' in data:
        episode.url = data['url']
    if 'is_favorite' in data:
        episode.is_favorite = data['is_favorite']
    if 'host' in data:
        episode.host = data['host']

    try:
        db.session.commit()
        flash("Episode erfolgreich aktualisiert!", "success")
        return jsonify({"message": "Episode erfolgreich aktualisiert!"}), 200
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Aktualisieren der Episode: {str(e)}", "danger")
        return jsonify({"error": f"Fehler beim Aktualisieren der Episode: {str(e)}"}), 500

@app.route('/delete_episode/<int:episode_id>', methods=['DELETE'])
@login_required
def delete_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    try:
        db.session.delete(episode)
        db.session.commit()
        flash("Episode erfolgreich gelöscht", "success")
        return jsonify({"message": "Episode erfolgreich gelöscht"}), 204
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Löschen der Episode: {str(e)}", "danger")
        return jsonify({"error": f"Fehler beim Löschen der Episode: {str(e)}"}), 500

@app.route('/import_feeds_xlsx', methods=['POST'])
@login_required
def import_feeds_xlsx():
    data = request.json
    imported_count = 0
    errors = []

    for feed_data_entry in data:
        feed_url = feed_data_entry.get('url')
        if not feed_url:
            errors.append(f"Skipping entry due to missing URL: {feed_data_entry}")
            continue

        existing_feed = PodcastFeed.query.filter_by(url=feed_url).first()

        # Versuche, den Feed zu parsen, auch wenn er schon existiert, um aktuelle Daten zu bekommen
        parsed_feed_data, episodes_data = parse_rss_feed(feed_url)

        if not parsed_feed_data:
            errors.append(f"Failed to parse RSS feed or invalid URL for {feed_url}")
            continue

        try:
            if existing_feed:
                # KORREKTUR: Name und Topic nur aktualisieren, wenn sie nicht bereits manuell gesetzt wurden
                if existing_feed.name == existing_feed.url or existing_feed.name == 'Unbekannter Podcast':
                    existing_feed.name = parsed_feed_data.get('name', existing_feed.name)
                
                if parsed_feed_data.get('topic') is not None and (existing_feed.topic is None or existing_feed.topic == parsed_feed_data['topic']):
                    existing_feed.topic = parsed_feed_data['topic']

                existing_feed.is_active = feed_data_entry.get('is_active', existing_feed.is_active)
                existing_feed.last_checked = datetime.now()
                existing_feed.homepage_url = parsed_feed_data.get('homepage_url', existing_feed.homepage_url)
                db.session.commit()

                # Delete old episodes for this feed to avoid duplicates during import
                Episode.query.filter_by(feed_id=existing_feed.id).delete()
                db.session.commit()

                current_feed = existing_feed
                message = f"Feed '{current_feed.name}' (URL: {feed_url}) aktualisiert."
            else:
                # Add new feed
                new_feed = PodcastFeed(
                    url=feed_url,
                    name=parsed_feed_data.get('name', feed_url), # Verwende Parsed-Namen, sonst URL
                    topic=parsed_feed_data.get('topic'),
                    is_active=feed_data_entry.get('is_active', True),
                    last_checked=datetime.now(),
                    homepage_url=parsed_feed_data.get('homepage_url')
                )
                db.session.add(new_feed)
                db.session.commit()
                current_feed = new_feed
                message = f"Feed '{current_feed.name}' (URL: {feed_url}) hinzugefügt."
            
            imported_count += 1
            print(f"Import success: {message}")

            # Add episodes for the current feed
            for ep_data in episodes_data:
                ep_data['feed_id'] = current_feed.id
                ep_data.setdefault('is_favorite', False)
                episode = Episode(**ep_data)
                db.session.add(episode)
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            errors.append(f"Database error for {feed_url}: {str(e)}")

    if errors:
        return jsonify({"message": f"Import finished with {imported_count} successes and {len(errors)} errors.", "errors": errors}), 200
    else:
        return jsonify({"message": f"Alle {imported_count} Feeds erfolgreich importiert!"}), 200

@app.route('/export_feeds_xlsx', methods=['GET'])
@login_required
def export_feeds_xlsx():
    feeds = PodcastFeed.query.all()
    # Daten für XLSX aufbereiten (Beispielstruktur)
    data = []
    for feed in feeds:
        data.append({
            "Feed URL": feed.url,
            "Podcast Name": feed.name,
            "Topic": feed.topic,
            "Homepage URL": feed.homepage_url,
            "Is Active": "Yes" if feed.is_active else "No",
            "Last Checked": feed.last_checked.strftime('%Y-%m-%d %H:%M:%S') if feed.last_checked else ''
        })
    # Hier würde die Logik zum Erstellen und Senden der XLSX-Datei folgen
    # Für den Moment senden wir nur eine Erfolgsmeldung zurück
    flash("Export-Funktion wird in einem zukünftigen Schritt implementiert.", "info")
    return jsonify({"message": "Export-Funktion wird in einem zukünftigen Schritt implementiert. (Backend)"})


if __name__ == '__main__':
    with app.app_context():
        print("DEBUG: SQLALCHEMY_DATABASE_URI wird verwendet:", app.config['SQLALCHEMY_DATABASE_URI'])
        print("DEBUG: Versuche, Datenbanktabellen zu erstellen (db.create_all())...")
        try:
            db.create_all()
            print("DEBUG: Datenbanktabellen erfolgreich erstellt oder existieren bereits.")
            # Füge hier optional einen Test-Feed hinzu, wenn die DB leer ist
            # if PodcastFeed.query.count() == 0:
            #     print("DEBUG: Keine Feeds gefunden. Füge einen Beispiel-Feed hinzu.")
            #     example_feed = PodcastFeed(
            #         url="http://feeds.feedburner.com/PodCastDownload", # Beispiel-URL
            #         name="Beispiel Podcast",
            #         topic="Tech",
            #         is_active=True,
            #         last_checked=datetime.now(),
            #         homepage_url="https://example.com/podcast"
            #     )
            #     db.session.add(example_feed)
            #     db.session.commit()
            #     print("DEBUG: Beispiel-Feed hinzugefügt.")
            #     # Optional: parse_rss_feed(example_feed.url) und Episoden hinzufügen
            #     # Dies würde jedoch Netzwerkzugriff erfordern und den Start verzögern.
        except Exception as e:
            print(f"FEHLER: Fehler beim Erstellen der Datenbanktabellen: {e}")
            
    # Standardmäßig Flask-Entwicklungsserver starten
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5000))
