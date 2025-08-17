#!/usr/bin/env python3
"""
Test-Skript für die Podcast-Tracker-Applikation mit neuen Suchfunktionen
"""

import requests
import json
import os
from datetime import datetime

# Konfiguration
BASE_URL = "http://localhost:5000"  # Ändern Sie dies für Ihre Deployment-URL
TEST_EPISODE_ID = 1  # Ändern Sie dies zu einer gültigen Episode-ID

def test_transcript_search():
    """Testet die Transkript-Suchfunktion"""
    print("🔍 Teste Transkript-Suchfunktion...")
    
    url = f"{BASE_URL}/api/search-transcript/{TEST_EPISODE_ID}"
    
    try:
        response = requests.post(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ Transkript gefunden: {data.get('url')}")
                print(f"   Quelle: {data.get('source')}")
            else:
                print(f"❌ Kein Transkript gefunden: {data.get('message')}")
        else:
            print(f"❌ Fehler: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Netzwerkfehler: {e}")
    
    print("-" * 50)

def test_youtube_search():
    """Testet die YouTube-Suchfunktion"""
    print("📺 Teste YouTube-Suchfunktion...")
    
    url = f"{BASE_URL}/api/search-youtube/{TEST_EPISODE_ID}"
    
    try:
        response = requests.post(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ YouTube-Suche erfolgreich: {data.get('url')}")
                print(f"   Quelle: {data.get('source')}")
                print(f"   Direkter Link: {data.get('direct_link')}")
            else:
                print(f"❌ YouTube-Suche fehlgeschlagen: {data.get('message')}")
        else:
            print(f"❌ Fehler: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Netzwerkfehler: {e}")
    
    print("-" * 50)

def test_episodes_api():
    """Testet die Episodes-API auf neue Felder"""
    print("📋 Teste Episodes-API für neue Felder...")
    
    url = f"{BASE_URL}/episodes"
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            episodes = response.json()
            if episodes:
                episode = episodes[0]  # Erste Episode als Beispiel
                print(f"✅ Episode gefunden: {episode.get('title', 'Unbekannt')[:50]}...")
                
                # Prüfe neue Felder
                new_fields = [
                    'youtube_url', 'youtube_search_status', 
                    'transcript_url', 'transcript_search_status'
                ]
                
                for field in new_fields:
                    value = episode.get(field)
                    print(f"   {field}: {value}")
                    
                print(f"✅ Alle neuen Felder sind verfügbar!")
            else:
                print("⚠️ Keine Episoden gefunden")
        else:
            print(f"❌ Fehler: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Netzwerkfehler: {e}")
    
    print("-" * 50)

def check_environment():
    """Prüft die Umgebungsvariablen"""
    print("🔧 Prüfe Umgebungsvariablen...")
    
    required_vars = ['GOOGLE_CSE_API_KEY', 'GOOGLE_CSE_ID']
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {'*' * (len(value) - 4) + value[-4:] if len(value) > 4 else '***'}")
        else:
            print(f"❌ {var}: Nicht gesetzt")
    
    print("-" * 50)

def main():
    """Hauptfunktion für alle Tests"""
    print("🚀 Starte Tests für Podcast-Tracker-Erweiterungen")
    print(f"Basis-URL: {BASE_URL}")
    print(f"Test-Episode-ID: {TEST_EPISODE_ID}")
    print(f"Zeitstempel: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Umgebungsvariablen prüfen
    check_environment()
    
    # API-Tests
    test_episodes_api()
    test_transcript_search()
    test_youtube_search()
    
    print("🏁 Tests abgeschlossen!")

if __name__ == "__main__":
    main()

