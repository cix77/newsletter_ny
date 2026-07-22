import os
import json
import time
import requests
import webbrowser
import pandas as pd
import warnings
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning
from openai import OpenAI

# Unschöne Parser-Warnungen stummschalten
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# ==========================================
# 1. SETUP & KONFIGURATION
# ==========================================
load_dotenv()

API_KEY = os.getenv("api_key", "").strip()

print("API-Key:", repr(API_KEY))

client = OpenAI(
    api_key=API_KEY,
    max_retries=3
)
HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Content-Type": "application/json"
}

EST_NOW = datetime.utcnow() - timedelta(hours=4)
days_de_short = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]
CURRENT_DAY_STR = days_de_short[EST_NOW.weekday()]

START_EST = EST_NOW.strftime('%Y-%m-%d')
END_EST = (EST_NOW + timedelta(days=7)).strftime('%Y-%m-%d')

print(f"⏰ [System] New York Zeit: {EST_NOW.strftime('%H:%M:%S')} ({CURRENT_DAY_STR})")
print(f"📅 [Zeitfenster] Suche Lineups von {START_EST} bis {END_EST} (EST)\n")

CONFIG_VENUES = {
    "RA_VENUES": {
        "Nowadays": "116241",
        "House of Yes": "105655",
        "Bossa Nova Civic Club": "66203",
        "99 Scott": "150035"
    },
    "WEB_FALLBACKS": {
        "SILO Brooklyn": "https://silobrooklyn.com",
        "Basement New York": "https://basementny.com",
        "Nowadays": "https://nowadays.nyc",
        "Public Records": "https://publicrecords.nyc",
        "Baby's All Right": "https://babysallright.com",
        "TV Eye": "https://www.tveyenyc.com",
        "Knockdown Center": "https://knockdown.center",
        "The Sultan Room": "https://www.thesultanroom.com",
        "Pioneer Works": "https://pioneerworks.org",
        "Bowery Ballroom": "https://www.boweryballroom.com",
        "Union Pool": "https://www.unionpool.com",
        "MoMA PS1": "https://www.moma.org/ps1",
        "Whitney Museum": "https://whitney.org",
        "Nublu": "https://www.nublu.net"
    }
}

# ==========================================
# 2. ISOLIERTE & ROBUSTE SCRAPER
# ==========================================

def scrape_ra_graphql():
    print("🌐 [Scraper 1/3] Abfrage Resident Advisor GraphQL...")
    events = []
    graphql_url = "https://ra.co/graphql"

    query = """
    query GET_VENUE_EVENTS($id: ID!) {
      venue(id: $id) {
        name
        events(type: FROMDATE) {
          title
          startTime
        }
      }
    }
    """
    
    for name, v_id in CONFIG_VENUES["RA_VENUES"].items():
        try:
            res = requests.post(
                graphql_url, 
                json={"query": query, "variables": {"id": str(v_id)}}, 
                headers=HEADERS_BROWSER, 
                timeout=6
            )
            if res.status_code == 200:
                res_data = res.json().get("data") or {}
                venue_data = res_data.get("venue")
                
                # Wasserfeste Typprüfung gegen NoneType-Abstürze
                if isinstance(venue_data, dict):
                    items = venue_data.get("events") or []
                    for item in items:
                        if isinstance(item, dict) and item.get("title"):
                            events.append({
                                "title": f"{item['title']} @ {name}",
                                "start_date": item.get("startTime", ""),
                                "source": "RA-GraphQL"
                            })
        except Exception:
            continue
            
    print(f"   -> {len(events)} Signale aus Resident Advisor gesammelt.")
    return events

def scrape_oh_my_rockness():
    print("🌐 [Scraper 2/3] Abfrage Oh My Rockness...")
    events = []
    try:
        res = requests.get("https://www.ohmyrockness.com/shows", headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for card in soup.select('.show-card')[:35]:
                title = card.select_one('.show-card-title')
                venue = card.select_one('.show-card-venue')
                date_elem = card.select_one('.show-card-date')
                date_str = date_elem.get_text().strip() if date_elem else ""
                
                if title and venue:
                    events.append({
                        "title": f"{title.get_text().strip()} @ {venue.get_text().strip()}",
                        "start_date": date_str,
                        "source": "Oh My Rockness"
                    })
    except Exception as e:
        print(f"   ❌ OMR Fehler: {e}")
    print(f"   -> {len(events)} Signale aus Oh My Rockness gesammelt.")
    return events

def scrape_nyc_noise():
    print("🌐 [Scraper 3/3] Abfrage NYC Noise...")
    events = []
    try:
        res = requests.get("https://nyc-noise.com/", headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for line in soup.get_text().split('\n'):
                cleaned = line.strip()
                if 25 < len(cleaned) < 180 and ("@" in cleaned or " at " in cleaned):
                    if not any(bad in cleaned.lower() for bad in ["raffle", "lessons", "fundraiser", "newsletter"]):
                        events.append({"title": cleaned, "source": "NYC Noise"})
    except Exception as e:
        print(f"   ❌ NYC Noise Fehler: {e}")
    print(f"   -> {len(events)} Signale aus NYC Noise gesammelt.")
    return events

# ==========================================
# 3. GPT-4o KURATION (MIT RETRY & TIMEOUT)
# ==========================================
def curate_events_via_llm(pool):
    if not pool:
        return []
    print(f"\n📡 [Scoring-Engine] GPT-4o kuratiert {len(pool)} Roh-Kandidaten...")
    
    prompt = f"""
    Du bist Musikjournalist in NYC für einen wöchentlichen Underground-Guide. Erstelle ein Wochenprogramm (MO bis SO).
    
    REGELN:
    1. Filter seelenlosen Müll (Tanzkurse, Musikunterricht, Spendenaktionen) strikt heraus.
    2. Bevorzuge Club-Events, Raves, Live-Konzerte und Ausstellungen.
    3. TONFALL: Sprich den Leser ausnahmslos mit "Du" an (NIEMALS "Sie").
    4. WOCHENTAG: Bestimme den zweistelligen Wochentag (MO, DI, MI, DO, FR, SA, SO) aus dem Event-Titel oder Datum.
    
    POOL:
    {json.dumps(pool)}
    
    Antworte AUSSCHLIESSLICH als gültiges JSON:
    {{
        "scored_events": [
            {{
                "category": "partys",
                "day": "FR",
                "header_line": "Artist / Event - Venue",
                "desc": "Kurze Beschreibung auf Deutsch in Duz-Form.",
                "overall_score": 85
            }}
        ]
    }}
    """
    for attempt in range(2):
        try:
            res = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                timeout=25.0
            )
            raw_content = res.choices[0].message.content.strip()
            bt = chr(96) * 3
            raw_content = raw_content.replace(bt + "json", "").replace(bt, "").strip()
            return json.loads(raw_content).get("scored_events", [])
        except Exception as e:
            print(f"   ⚠️ Versuch {attempt+1} fehlgeschlagen ({e}). Retrying...")
            time.sleep(2)
            
    print("   ❌ GPT-4o Kuration endgültig fehlgeschlagen.")
    return []

# ==========================================
# 4. HTML NEWSLETTER GENERIERUNG
# ==========================================
def build_html_newsletter(data):
    days_de = ["MONTAG", "DIENSTAG", "MITTWOCH", "DONNERSTAG", "FREITAG", "SAMSTAG", "SONNTAG"]
    months_de = ["JAN", "FEB", "MÄZ", "APR", "MAI", "JUN", "JUL", "AUG", "SEP", "OKT", "NOV", "DEZ"]
    date_str = f"WEEKLY UNDERGROUND GUIDE // AB {days_de[EST_NOW.weekday()]}, {EST_NOW.day}. {months_de[EST_NOW.month-1]} {EST_NOW.year}"

    mono_font = "'SFMono-Regular', Consolas, monospace"
    sans_font = "system-ui, sans-serif"

    html = f"""
    <html>
    <head><meta charset='utf-8'></head>
    <body style='background:#0d0d0d; color:#fff; font-family:{sans_font}; padding:40px; max-width:750px; margin:0 auto; line-height:1.5;'>
    <h1 style='color:#00ff66; font-size:2.8em; font-weight:900; margin-bottom:5px; letter-spacing:-1px;'>Underground NL New York</h1>
    <p style='font-family:{mono_font}; color:#ff007f; margin-bottom:50px; font-weight:bold;'>{date_str}</p>
    """
    
    categories = ["partys", "musik", "kunst"]
    
    for cat in categories:
        html += f"<h2 style='font-size:1.8em; font-weight:900; margin-top:40px; color:#fff; border-bottom:2px solid #262626; padding-bottom:8px;'>{cat.capitalize()}</h2>"
        events = data.get(cat, []) if isinstance(data, dict) else []
        
        if events:
            for show in events:
                header = show.get('header_line', '')
                
                link = "https://www.google.com/search?q=" + requests.utils.quote(header)
                for venue, verified_url in CONFIG_VENUES["WEB_FALLBACKS"].items():
                    if venue.lower() in header.lower():
                        link = verified_url
                        break
                
                day_str = show.get('day', 'MO').upper()
                
                html += "<div style='padding:16px 0; border-bottom:1px solid #1a1a1a;'>"
                html += "<div style='margin-bottom:6px;'>"
                html += f"<span style='font-family:{mono_font}; color:#ff007f; font-weight:bold; display:inline-block; width:35px;'>{day_str}</span>"
                html += f"<span style='font-weight:800; font-size:1.15em;'>"
                html += f"<a href='{link}' target='_blank' style='color:#fff; text-decoration:none;'>{header}</a>"
                html += "</span></div>"
                html += f"<div style='color:#bbb; font-size:0.95em; padding-left:35px;'>{show.get('desc')}</div>"
                html += "</div>"
        else:
            html += f"<p style='color:#555; font-family:{mono_font}; font-size:0.85em;'>// Keine Events ausgewählt</p>"
                
    html += "</body></html>"
    path = os.path.expanduser("~/Desktop/index_dyce.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n📍 Newsletter erfolgreich generiert unter: {path}")
    webbrowser.open("file://" + path)

# ==========================================
# 5. PIPELINE EXECUTION
# ==========================================
if __name__ == "__main__":
    raw_pool = []
    
    raw_pool.extend(scrape_ra_graphql())
    raw_pool.extend(scrape_oh_my_rockness())
    raw_pool.extend(scrape_nyc_noise())
    
    if not raw_pool:
        print("❌ Keine Daten extrahiert.")
        exit(1)
        
    df = pd.DataFrame(raw_pool)
    df.drop_duplicates(subset=['title'], inplace=True)
    final_pool = df.to_dict(orient="records")
    
    print(f"\n📊 [Deduplication] Gesamtpool: {len(final_pool)} verifizierte Kandidaten geladen.")
    
    scored_list = curate_events_via_llm(final_pool)
    final_selection = {"partys": [], "musik": [], "kunst": []}
    
    if scored_list:
        df_scored = pd.DataFrame(scored_list)
        df_scored["overall_score"] = pd.to_numeric(df_scored["overall_score"], errors='coerce').fillna(0)
        df_scored.sort_values(by="overall_score", ascending=False, inplace=True)
        
        # Schwellenwert für gefülltes Wochenprogramm
        df_scored = df_scored[df_scored["overall_score"] >= 25]
        
        for cat in ["partys", "musik", "kunst"]:
            final_selection[cat] = df_scored[df_scored["category"] == cat].to_dict(orient="records")

    build_html_newsletter(final_selection)