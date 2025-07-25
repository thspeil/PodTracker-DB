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
from urllib.parse import urlparse # Import for isValidUrl

# Lade Umgebungsvariablen aus .env-Datei (für lokale Entwicklung, in Codespaces durch Secrets überschrieben)
load_dotenv()

# Flask-Anwendung initialisieren
# 'static_folder' verweist auf den Ordner für statische Dateien (CSS, JS, Bilder, Favicon)
# 'template_folder' verweist auf den Ordner für HTML-Templates (hier das Hauptverzeichnis '.')
app = Flask(__name__, static_folder='static', template_folder='.')

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY_FLASK_LOGIN', 'your_super_secret_key_that_you_must_change_in_production')
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'podcast_tracker.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(minutes=20)

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Bitte melden Sie sich an, um diese Seite zu sehen."
login_manager.login_message_category = "warning"

# Benutzer-Modell für Flask-Login
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    @staticmethod
    def get_user_by_username(username):
        if username == "user1":
            hashed_pw_for_user1 = """scrypt:32768:8:1$anilOJC7MTH87cwT$624d07e2737d25657bff2e6d516bd38cdee48729cd9421b22b8f6a30f3e49a3627e3a334718f84216a6698bf0c55a21043f63fe4c73c9007ae212d6d657929d3"""
            return User(id=1, username="user1", password_hash=hashed_pw_for_user1)
        return None

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    if user_id == '1':
        hashed_pw_for_user1 = """scrypt:32768:8:1$anilOJC7MTH87cwT$624d07e2737d25657bff2e6d516bd38cdee48729cd9421b22b8f6a30f3e49a3627e3a334718f84216a6698bf0c55a21043f63fe4c73c9007ae212d6d657929d3"""
        return User(id=1, username="user1", password_hash=hashed_pw_for_user1)
    return None

CORS(app)

# Definition des Datenmodells für Podcast-Feeds
class PodcastFeed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), unique=True, nullable=False)
    name = db.Column(db.String(255))
    topic = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    homepage_url = db.Column(db.String(500)) 
    episodes = db.relationship('Episode', backref='feed', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<PodcastFeed {self.url}>'

# Definition des Datenmodells für Episoden
class Episode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    feed_id = db.Column(db.Integer, db.ForeignKey('podcast_feed.id'), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    pub_date = db.Column(db.DateTime)
    url = db.Column(db.String(500), unique=True, nullable=False)
    is_favorite = db.Column(db.Boolean, default=False)
    host = db.Column(db.String(255))

    def __repr__(self):
        return f'<Episode {self.title}>'

# Hilfsfunktion zur URL-Validierung (korrigierte Python-Version)
def isValidUrl(url_string):
    if not isinstance(url_string, str): # Sicherstellen, dass es ein String ist
        return False
    try:
        result = urlparse(url_string)
        # Überprüfe, ob sowohl ein Schema (http, https) als auch ein Netzwerk-Ort (Domain) vorhanden ist
        return all([result.scheme, result.netloc])
    except ValueError: # urlparse kann ValueError werfen
        return False
    except Exception as e:
        print(f"DEBUG: isValidUrl unexpected error for '{url_string}': {e}")
        return False

# Hilfsfunktion zum Parsen von RSS-Feeds
def parse_rss_feed(feed_url):
    """
    Ruft einen RSS-Feed ab und parst ihn, um Episodendaten und die Homepage-URL zu extrahieren.
    Priorisiert spezifischere Homepage-URLs.
    """
    print(f"DEBUG: Starte Parsing für Feed: {feed_url}")
    try:
        response = requests.get(feed_url, timeout=15) # Timeout leicht erhöht
        response.raise_for_status() # Löst einen HTTPError für schlechte Antworten (4xx oder 5xx) aus
        
        # XML-Inhalt parsen
        root = ET.fromstring(response.content)
        
        episodes_data = []
        # Namespaces für verschiedene RSS-Erweiterungen
        namespaces = {
            'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
            'atom': 'http://www.w3.org/2005/Atom',
            'googleplay': 'http://www.google.com/schemas/play-podcasts/1.0', # Korrigierter Google Play Namespace
            'media': 'http://search.yahoo.com/mrss/', # Hinzugefügt für media:content
            'webfeeds': 'http://webfeeds.org/rss/1.0' # Für webfeeds:url (Alternative Homepage-URL)
        }

        # --- Homepage URL extrahieren (Hierarchie der Präferenzen) ---
        homepage_url = None

        # 1. itunes:new-feed-url (falls Feed umgezogen ist)
        new_feed_url_tag = root.find('.//itunes:new-feed-url', namespaces)
        if new_feed_url_tag is not None and new_feed_url_tag.text and isValidUrl(new_feed_url_tag.text):
            homepage_url = new_feed_url_tag.text
            print(f"DEBUG: Homepage found (itunes:new-feed-url): {homepage_url}")

        # 2. itunes:url oder itunes:feedlink (spezifisch für Podcast-Homepage)
        if homepage_url is None:
            itunes_url_tag = root.find('.//channel/itunes:url', namespaces)
            if itunes_url_tag is None:
                itunes_url_tag = root.find('.//channel/itunes:feedlink', namespaces) # itunes:feedlink ist seltener
            if itunes_url_tag is not None and itunes_url_tag.text and isValidUrl(itunes_url_tag.text):
                homepage_url = itunes_url_tag.text
                print(f"DEBUG: Homepage found (itunes): {homepage_url}")
        
        # 3. atom:link rel="alternate" (kann auch auf Homepage verweisen, oft der "Standard" in neueren Feeds)
        if homepage_url is None:
            # Suche nach atom:link mit rel="alternate" und type="text/html"
            atom_link = root.find('.//channel/atom:link[@rel="alternate"][@type="text/html"]', namespaces)
            if atom_link is not None and 'href' in atom_link.attrib and isValidUrl(atom_link.attrib['href']):
                homepage_url = atom_link.attrib['href']
                print(f"DEBUG: Homepage found (atom html): {homepage_url}")

        # 4. googleplay:link (auch spezifischer)
        if homepage_url is None:
            googleplay_link = root.find('.//channel/googleplay:link', namespaces)
            if googleplay_link is not None and 'href' in googleplay_link.attrib and isValidUrl(googleplay_link.attrib['href']):
                homepage_url = googleplay_link.attrib['href']
                print(f"DEBUG: Homepage found (googleplay): {homepage_url}")

        # 5. webfeeds:url (spezifisch für die Website)
        if homepage_url is None:
            webfeeds_url_tag = root.find('.//webfeeds:url', namespaces)
            if webfeeds_url_tag is not None and webfeeds_url_tag.text and isValidUrl(webfeeds_url_tag.text):
                homepage_url = webfeeds_url_tag.text
                print(f"DEBUG: Homepage found (webfeeds): {homepage_url}")


        # 6. Fallback: Standard <channel><link> (generischer Link, kann auch der RSS-Feed selbst sein, aber oft die Homepage)
        if homepage_url is None:
            channel_link = root.find('.//channel/link')
            if channel_link is not None and channel_link.text and isValidUrl(channel_link.text):
                homepage_url = channel_link.text
                print(f"DEBUG: Homepage found (channel link fallback): {homepage_url}")
            
        # Wenn immer noch keine Homepage_url gefunden wurde, setze auf None
        if homepage_url is None:
            print(f"Warnung: Keine spezifische Homepage-URL für {feed_url} gefunden. Verbleibt None.")

        # --- Episoden-Daten extrahieren ---
        for item in root.findall('.//item'):
            title = item.find('title').text if item.find('title') is not None else 'No Title'
            description = item.find('description').text if item.find('description') is not None else 'No Description'
            pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else None
            
            episode_url = None
            
            # Priorität der Episode URL: enclosure (audio/video) > media:content (audio/video) > guid (wenn isPermalink="true") > item/link (webpage)
            
            # 1. Check for standard <enclosure> (often the direct audio file)
            enclosure = item.find('enclosure')
            if enclosure is not None and 'url' in enclosure.attrib and isValidUrl(enclosure.attrib['url']):
                episode_url = enclosure.attrib['url']
                # print(f"DEBUG: Found episode URL in enclosure for '{title}': {episode_url}")
            
            # 2. Check for media:content (common in some feeds for media files)
            if episode_url is None:
                media_content = item.find('media:content', namespaces)
                if media_content is not None and 'url' in media_content.attrib and isValidUrl(media_content.attrib['url']):
                    episode_url = media_content.attrib['url']
                    # print(f"DEBUG: Found episode URL in media:content for '{title}': {episode_url}")

            # 3. Check for <guid> if it's a permalink (often direct link to episode page or audio)
            if episode_url is None:
                guid_tag = item.find('guid')
                if guid_tag is not None and guid_tag.text and isValidUrl(guid_tag.text):
                    # Nur verwenden, wenn guid als Permalink gedacht ist (standard oder explizit "true")
                    if guid_tag.attrib.get('isPermalink', 'true').lower() == 'true':
                        episode_url = guid_tag.text
                        # print(f"DEBUG: Found episode URL in guid for '{title}': {episode_url}")
                
            # 4. Fallback to item/link. This often points to the episode's webpage, not the audio file.
            # We'll only use it if no other media URL was found and if it's a valid URL.
            if episode_url is None:
                item_link_tag = item.find('link')
                if item_link_tag is not None and item_link_tag.text and isValidUrl(item_link_tag.text):
                    episode_url = item_link_tag.text
                    # print(f"DEBUG: Found episode URL in item/link fallback for '{title}': {episode_url}")
                else:
                    print(f"DEBUG: Item link for '{title}' is not a valid URL or missing.")


            host = None
            itunes_author = item.find('itunes:author', namespaces)
            if itunes_author is not None:
                host = itunes_author.text
            elif item.find('author') is not None: # Fallback zu RSS standard author
                host = item.find('author').text

            pub_date = None
            if pub_date_str:
                # Erweiterte Liste von Datumsformaten zum Parsen
                date_formats = [
                    '%a, %d %b %Y %H:%M:%S %Z',  # RFC 822 (e.g., Thu, 01 Jan 2020 00:00:00 GMT)
                    '%a, %d %b %Y %H:%M:%S %z',  # RFC 822 with UTC offset (e.g., Thu, 01 Jan 2020 00:00:00 +0000)
                    '%Y-%m-%dT%H:%M:%S%z',       # ISO 8601 with offset (e.g., 2020-01-01T00:00:00+00:00)
                    '%Y-%m-%dT%H:%M:%SZ',        # ISO 8601 with Z for UTC (e.g., 2020-01-01T00:00:00Z)
                    '%Y-%m-%d %H:%M:%S%z',       # YYYY-MM-DD HH:MM:SS+00:00
                    '%Y-%m-%d %H:%M:%S',         # YYYY-MM-DD HH:MM:SS (naive)
                    '%a, %d %b %Y %H:%M:%S %z',  # Another common RFC 822 variant (e.g., Mon, 01 Jan 2024 00:00:00 -0500)
                    '%d %b %Y %H:%M:%S',         # DD Mon YYYY HH:MM:SS (naive)
                    '%m/%d/%Y %H:%M:%S',         # MM/DD/YYYY HH:MM:SS (naive)
                    '%d.%m.%Y %H:%M',            # DD.MM.YYYY HH:MM (naive)
                    '%Y-%m-%d',                  # Just date (e.g., 2020-01-01)
                ]
                for fmt in date_formats:
                    try:
                        pub_date = datetime.strptime(pub_date_str, fmt)
                        # Für Zeitzonen-agnostische Formate oder solche ohne TZ-Info, UTC annehmen
                        if pub_date.tzinfo is None:
                            # Python's datetime.utcnow() returns naive datetime, so tzinfo must be manually handled
                            # For simplicity, if timezone is missing, we'll keep it naive for DB, unless a TZ is parsed.
                            pass # pub_date remains naive if not parsed with %z or %Z
                        break 
                    except ValueError:
                        continue 
                if pub_date is None:
                    print(f"Warnung: Datum konnte nicht geparst werden für '{title}': {pub_date_str}")
                
            if episode_url and isValidUrl(episode_url): # Nur Episoden mit einer gültigen URL hinzufügen
                episodes_data.append({
                    'title': title,
                    'description': description,
                    'pub_date': pub_date,
                    'url': episode_url,
                    'host': host
                })
            else:
                print(f"Warnung: Episode '{title}' ohne gültige URL '{episode_url}' übersprungen.")

        return episodes_data, homepage_url
    except requests.exceptions.RequestException as e:
        print(f"Fehler beim Abrufen des Feeds {feed_url}: {e}")
        return None, None
    except ET.ParseError as e:
        print(f"Fehler beim Parsen des XML-Feeds {feed_url}: {e}")
        return None, None
    except Exception as e:
        print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        return None, None

# API-Endpunkte

# Route zum Servieren der Haupt-HTML-Datei (Frontend)
@app.route('/')
@login_required
def serve_frontend():
    # Stellt die podcast_tracker-DB.html bereit, die im template_folder (root) liegt
    return render_template('podcast_tracker-DB.html')

# Routen für Login und Logout
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('serve_frontend')) # Wenn bereits eingeloggt, weiterleiten

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.get_user_by_username(username) # Hol den Benutzer aus deiner DB
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True) # "Remember Me" aktivieren
            flash('Erfolgreich eingeloggt!', 'success')
            return redirect(url_for('serve_frontend'))
        else:
            flash('Ungültiger Benutzername oder Passwort.', 'danger')
    return render_template('login.html') # Du brauchst ein login.html Template

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Erfolgreich ausgeloggt.', 'info')
    return redirect(url_for('login'))


# Route für Impressum
@app.route('/impressum')
def impressum():
    # Stellt die Impressum.html bereit, die im template_folder (root) liegt
    return render_template('Impressum.html')

# Route für Datenschutz
@app.route('/datenschutz')
def datenschutz():
    # Stellt die Datenschutz.html bereit, die im template_folder (root) liegt
    return render_template('Datenschutz.html')

# NEU: Route zum Servieren des Favicons
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.static_folder, 'favicon.ico')

# Feeds abrufen und hinzufügen
@app.route('/feeds', methods=['GET', 'POST'])
@login_required
def handle_feeds():
    if request.method == 'POST':
        data = request.json
        if not data or not 'url' in data:
            flash("URL für Feed fehlt", "danger")
            return jsonify({"error": "URL für Feed fehlt"}), 400

        feed_url = data['url']
        topic = data.get('topic', None)
        name = data.get('name', None)
        is_active = data.get('is_active', True)

        # NEU: Homepage URL extrahieren beim Hinzufügen
        episodes_data, homepage_url = parse_rss_feed(feed_url)
        # NEU: Bedingungen für das Hinzufügen/Aktualisieren eines Feeds gelockert.
        # Ein Feed wird hinzugefügt, wenn er parsen lässt (episodes_data != None)
        # ODER eine Homepage-URL gefunden wurde.
        # Wenn beides None ist (Fehler beim Abrufen/Parsen und keine Homepage), dann ist es ein Fehler.
        if episodes_data is None and homepage_url is None: 
            flash(f"Fehler beim Abrufen oder Parsen des RSS-Feeds: {feed_url}", "danger")
            return jsonify({"error": f"Fehler beim Abrufen oder Parsen des RSS-Feeds: {feed_url}"}), 400


        # Prüfen, ob Feed bereits existiert
        existing_feed = PodcastFeed.query.filter_by(url=feed_url).first()
        if existing_feed:
            try:
                # Wenn der Feed bereits existiert, aktualisiere Name, Thema, Aktiv-Status und Homepage URL
                # Aktualisiere nur, wenn ein neuer Wert vorhanden ist und der alte leer war, oder wenn explizit neue Werte kommen
                if name and (not existing_feed.name or existing_feed.name != name):
                    existing_feed.name = name
                if topic and (not existing_feed.topic or existing_feed.topic != topic):
                    existing_feed.topic = topic
                existing_feed.is_active = is_active # is_active immer aktualisieren
                existing_feed.homepage_url = homepage_url # Homepage URL aktualisieren, auch wenn None (um alte falsche zu überschreiben)
                db.session.commit()
                flash("Feed bereits vorhanden und aktualisiert", "info")
                return jsonify({"message": "Feed bereits vorhanden und aktualisiert", "id": existing_feed.id, "url": existing_feed.url, "name": existing_feed.name, "topic": existing_feed.topic, "is_active": existing_feed.is_active, "homepage_url": existing_feed.homepage_url}), 200
            except Exception as e:
                db.session.rollback()
                flash(f"Fehler beim Aktualisieren des bestehenden Feeds: {str(e)}", "danger")
                return jsonify({"error": f"Fehler beim Aktualisieren des bestehenden Feeds: {str(e)}"}), 500

        else: # Feed existiert noch nicht, neu hinzufügen
            new_feed = PodcastFeed(url=feed_url, name=name, topic=topic, is_active=is_active, homepage_url=homepage_url) # Homepage URL speichern
            db.session.add(new_feed)
            try:
                db.session.commit()
                flash("Feed hinzugefügt", "success")
                return jsonify({"message": "Feed hinzugefügt", "id": new_feed.id, "url": new_feed.url, "name": new_feed.name, "topic": new_feed.topic, "is_active": new_feed.is_active, "homepage_url": new_feed.homepage_url}), 201
            except Exception as e:
                db.session.rollback() 
                flash(f"Fehler beim Hinzufügen des Feeds: {str(e)}", "danger")
                print(f"Fehler beim Hinzufügen von Feed {feed_url}: {str(e)}")
                return jsonify({"error": f"Fehler beim Hinzufügen des Feeds: {str(e)}"}), 500
    
    else: # GET-Anfrage
        # NEU: Sortierung nach Thema und dann nach Name
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
                'last_checked': feed.last_checked.isoformat() if feed.last_checked else None,
                'homepage_url': feed.homepage_url # NEU: Homepage URL zurückgeben
            })
        return jsonify(feeds_data)

# Feed aktualisieren (PUT)
@app.route('/feeds/<int:feed_id>', methods=['PUT'])
@login_required
def update_feed(feed_id):
    feed = PodcastFeed.query.get_or_404(feed_id)
    data = request.json
    
    try:
        if 'url' in data:
            feed.url = data['url']
        if 'name' in data:
            feed.name = data['name']
        if 'topic' in data:
            feed.topic = data['topic']
        if 'is_active' in data:
            feed.is_active = bool(data['is_active'])
        # NEU: Homepage URL kann auch über PUT aktualisiert werden, falls nötig
        if 'homepage_url' in data:
            feed.homepage_url = data['homepage_url']
        
        db.session.commit()
        flash("Feed aktualisiert", "success")
        return jsonify({"message": "Feed aktualisiert", "id": feed.id, "url": feed.url, "name": feed.name, "topic": feed.topic, "is_active": feed.is_active, "homepage_url": feed.homepage_url}), 200
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Aktualisieren des Feeds: {str(e)}", "danger")
        return jsonify({"error": f"Fehler beim Aktualisieren des Feeds: {str(e)}"}), 500

# Feed löschen (DELETE)
@app.route('/feeds/<int:feed_id>', methods=['DELETE'])
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


# NEUER ENDPUNKT: Feeds aus XLSX importieren
@app.route('/import_feeds_xlsx', methods=['POST'])
@login_required
def import_feeds_xlsx():
    data = request.json
    if not data or not isinstance(data, list):
        flash("Ungültiges Datenformat. Erwartet wird eine Liste von Feeds.", "danger")
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
            flash(f"Feed ohne URL übersprungen: {feed_data}", "warning")
            continue

        episodes_data_from_rss, homepage_url = parse_rss_feed(feed_url)
        # Auch hier: Lockere die Bedingung. Add/update Feed auch, wenn keine Episoden gefunden wurden,
        # aber Homepage_url gefunden wurde, oder wenn es ein Problem beim Parsen gab, aber der Feed selbst ok ist.
        if episodes_data_from_rss is None and homepage_url is None: 
            errors.append(f"Fehler beim Abrufen/Parsen des RSS-Feeds (Import): {feed_url}")
            flash(f"Fehler beim Abrufen/Parsen des RSS-Feeds (Import): {feed_url}", "danger")
            continue


        existing_feed = PodcastFeed.query.filter_by(url=feed_url).first()

        if existing_feed:
            try:
                # Korrektur der Zuweisung: feed_name anstatt name, feed_topic anstatt topic
                if feed_name and (not existing_feed.name or existing_feed.name != feed_name): 
                    existing_feed.name = feed_name
                if feed_topic and (not existing_feed.topic or existing_feed.topic != feed_topic): 
                    existing_feed.topic = feed_topic
                existing_feed.is_active = feed_is_active
                existing_feed.homepage_url = homepage_url
                db.session.commit()
                updated_count += 1
                feeds_to_refresh_ids.append(existing_feed.id)
            except Exception as e:
                db.session.rollback()
                errors.append(f"Fehler beim Aktualisieren von Feed {feed_url}: {str(e)}")
                print(f"Fehler beim Aktualisieren von Feed {feed_url}: {str(e)}")
                flash(f"Fehler beim Aktualisieren von Feed {feed_url}: {str(e)}", "danger")

        else:
            new_feed = PodcastFeed(url=feed_url, name=feed_name, topic=feed_topic, is_active=feed_is_active, homepage_url=homepage_url)
            db.session.add(new_feed)
            try:
                db.session.commit()
                imported_count += 1
                feeds_to_refresh_ids.append(new_feed.id)
            except Exception as e:
                db.session.rollback() 
                errors.append(f"Fehler beim Hinzufügen von Feed {feed_url}: {str(e)}")
                print(f"Fehler beim Hinzufügen von Feed {feed_url}: {str(e)}")
                flash(f"Fehler beim Hinzufügen von Feed {feed_url}: {str(e)}", "danger")


    refreshed_episodes_count = 0
    successful_feed_refreshes = 0
    failed_feed_refreshes = 0

    for feed_id in feeds_to_refresh_ids:
        feed = PodcastFeed.query.get(feed_id)
        if feed and feed.is_active:
            episodes_data, _ = parse_rss_feed(feed.url) 
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
                try:
                    feed.last_checked = datetime.utcnow()
                    db.session.commit()
                    refreshed_episodes_count += new_episodes_for_feed_count
                    successful_feed_refreshes += 1
                except Exception as e:
                    db.session.rollback()
                    errors.append(f"Fehler beim Speichern der Episoden für Feed {feed.url}: {str(e)}")
                    print(f"Fehler beim Speichern der Episoden für Feed {feed.url}: {str(e)}")
                    flash(f"Fehler beim Speichern der Episoden für Feed {feed.url}: {str(e)}", "danger")
                    failed_feed_refreshes += 1
            else:
                errors.append(f"Fehler beim Aktualisieren der Episoden für Feed {feed.url}: Keine Daten gefunden oder Parsen fehlgeschlagen.")
                flash(f"Fehler beim Aktualisieren der Episoden für Feed {feed.url}: Keine Daten gefunden oder Parsen fehlgeschlagen.", "danger")
                failed_feed_refreshes += 1

    message_parts = []
    if imported_count > 0:
        message_parts.append(f"{imported_count} neu importiert")
    if updated_count > 0:
        message_parts.append(f"{updated_count} aktualisiert")
    if refreshed_episodes_count > 0:
        message_parts.append(f"{refreshed_episodes_count} neue Episoden hinzugefügt")
    if failed_feed_refreshes > 0:
        message_parts.append(f"{failed_feed_refreshes} Feed-Aktualisierungen fehlgeschlagen")

    final_message = "Feeds importiert. " + ", ".join(message_parts) if message_parts else "Keine Feeds importiert."
    flash(final_message, "success" if not errors else "warning")

    return jsonify({
        "message": final_message,
        "imported_count": imported_count,
        "updated_count": updated_count,
        "refreshed_episodes_count": refreshed_episodes_count,
        "errors": errors
    }), 200


# Alle Episoden abrufen
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

# Episode aktualisieren (PUT)
@app.route('/episodes/<int:episode_id>', methods=['PUT'])
@login_required
def update_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    data = request.json
    
    try:
        if 'title' in data:
            episode.title = data['title']
        if 'description' in data:
            episode.description = data['description']
        if 'pub_date' in data:
            try:
                episode.pub_date = datetime.fromisoformat(data['pub_date'])
            except ValueError:
                flash("Ungültiges Datumsformat für pub_date", "danger")
                return jsonify({"error": "Ungültiges Datumsformat für pub_date"}), 400
        if 'url' in data:
            episode.url = data['url']
        if 'is_favorite' in data:
            episode.is_favorite = bool(data['is_favorite'])
        if 'host' in data:
            episode.host = data['host']
            
        db.session.commit()
        flash("Episode aktualisiert", "success")
        return jsonify({"message": "Episode aktualisiert", "id": episode.id, "title": episode.title, "is_favorite": episode.is_favorite, "host": episode.host}), 200
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Aktualisieren der Episode: {str(e)}", "danger")
        return jsonify({"error": f"Fehler beim Aktualisieren der Episode: {str(e)}"}), 500

# Episode löschen (DELETE)
@app.route('/episodes/<int:episode_id>', methods=['DELETE'])
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
        flash(f"Fehler beim Löschen des Feeds: {str(e)}", "danger")
        return jsonify({"error": f"Fehler beim Löschen des Feeds: {str(e)}"}), 500


if __name__ == '__main__':
    # Initialisiere die Datenbank und erstelle Tabellen, falls nicht vorhanden
    # ACHTUNG: Dies wird NUR ausgeführt, wenn app.py direkt gestartet wird (z.B. python app.py)
    # Für Produktionsumgebungen (Cloud Run mit Gunicorn) muss db.create_all() im start.sh ausgeführt werden!
    with app.app_context():
        print("DEBUG: SQLALCHEMY_DATABASE_URI wird verwendet:", app.config['SQLALCHEMY_DATABASE_URI'])
        print("DEBUG: Versuche, Datenbanktabellen zu erstellen (db.create_all())...")
        try:
            db.create_all()
            print("DEBUG: Datenbanktabellen erfolgreich erstellt oder existieren bereits.")
        except Exception as e:
            print(f"FEHLER: Fehler beim Erstellen der Datenbanktabellen: {e}")
            
    # Standardmäßig Flask-Entwicklungsserver starten
    # In Produktion wird Gunicorn dies übernehmen
    app.run(debug=True, host='0.0.0.0')

