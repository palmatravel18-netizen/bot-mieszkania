import requests
from bs4 import BeautifulSoup
import time
import json
import os
import asyncio
import re
from telegram import Bot
from datetime import datetime, timedelta
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==========================================
# KONFIGURACJA 
# ==========================================
TELEGRAM_BOT_TOKEN = '8834803275:AAGcWnR8ujcknQJ2hM_n0vwn2veM22OTnBs'
TELEGRAM_CHAT_ID = '8277719275' 

MAX_CENA_GWH_WARM = 1200 
MAX_CENA_NHW_KALT = 1000 
MIN_POKOJE = 2        
MIN_METRAZ = 50       
DZIELNICE = ["Sachsenhausen-Nord", "Sachsenhausen-Süd", "Sachsenhausen", "Niederrad"] 

INTERWAL_SPRAWDZANIA_SEKUNDY = 60 
PLIK_HISTORII = 'znalezione_mieszkania.json' 
RAPORT_CO_ILE_GODZIN = 24 

bot = Bot(token=TELEGRAM_BOT_TOKEN)

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 10000))
    print(f"Uruchamiam serwer na porcie {port}")
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

def wczytaj_historie():
    if os.path.exists(PLIK_HISTORII):
        with open(PLIK_HISTORII, 'r') as f:
            return json.load(f)
    return []

def zapisz_historie(historia):
    with open(PLIK_HISTORII, 'w') as f:
        json.dump(historia, f)

def czy_pasuje_dzielnica(tekst):
    if not DZIELNICE: return True
    return any(d.lower() in tekst.lower() for d in DZIELNICE)

async def wyslij_powiadomienie(tytul, link, cena, pokoje, metraz, zrodlo):
    msg = f"🚨 <b>NOWE MIESZKANIE! ({zrodlo})</b>\n\n<b>Cena:</b> {cena} €\n👉 <a href='{link}'>Zobacz ofertę</a>"
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='HTML')
    except Exception as e:
        print(f"Błąd wysyłania: {e}")

def sprawdz_gwh():
    nowe_oferty = []
    url = "https://www.gwh.de/mietangebote"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        for oferta in soup.select('.estate-item, .item, .teaser'):
            tekst = oferta.get_text(separator=' ', strip=True)
            link_tag = oferta.find('a', href=True)
            if not link_tag: continue
            link = "https://www.gwh.de" + link_tag['href']
            cena_match = re.search(r'([\d\.,]+)\s*€', tekst)
            if cena_match:
                cena = float(cena_match.group(1).replace('.', '').replace(',', '.'))
                if cena <= MAX_CENA_GWH_WARM and czy_pasuje_dzielnica(tekst):
                    nowe_oferty.append({'id': f"gwh_{link[-10:]}", 'link': link, 'cena': cena, 'zrodlo': 'GWH'})
        return nowe_oferty
    except Exception as e:
        print(f"Błąd GWH: {e}")
        return []

def sprawdz_nhw():
    nowe_oferty = []
    url = "https://www.nhw.de/wohnungsangebote"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        for link_tag in soup.find_all('a', href=re.compile(r'/zuhause-finden/immobilie/')):
            link = "https://www.nhw.de" + link_tag['href']
            kontener = link_tag.find_parent('div')
            tekst = kontener.get_text(separator=' ', strip=True) if kontener else link_tag.get_text()
            cena_match = re.search(r'([\d\.,]+)\s*€', tekst)
            if cena_match:
                cena = float(cena_match.group(1).replace('.', '').replace(',', '.'))
                if cena <= MAX_CENA_NHW_KALT and czy_pasuje_dzielnica(tekst):
                    nowe_oferty.append({'id': f"nhw_{link[-10:]}", 'link': link, 'cena': cena, 'zrodlo': 'NHW'})
        return nowe_oferty
    except Exception as e:
        print(f"Błąd NHW: {e}")
        return []

async def main():
    # Startujemy serwer w tle
    threading.Thread(target=run_server, daemon=True).start()
    
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ <b>Bot wystartował!</b>", parse_mode='HTML')
    except Exception as e:
        print(f"Błąd Telegrama: {e}")
        
    czas_raportu = datetime.now()
    
    print("--- Pętla główna bota uruchomiona ---")
    
    while True:
        try:
            print("--- Sprawdzam nowe oferty... ---")
            historia = wczytaj_historie()
            wszystkie = sprawdz_gwh() + sprawdz_nhw()
            print(f"Znaleziono {len(wszystkie)} ofert na stronach.")
            
            nowe = [o for o in wszystkie if o['id'] not in historia]
            for oferta in nowe:
                await wyslij_powiadomienie("Mieszkanie", oferta['link'], oferta['cena'], 0, 0, oferta['zrodlo'])
                historia.append(oferta['id'])
            zapisz_historie(historia)
            
            if (datetime.now() - czas_raportu).total_seconds() >= (RAPORT_CO_ILE_GODZIN * 3600):
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ Raport: Bot nadal działa.", parse_mode='HTML')
                czas_raportu = datetime.now()
        except Exception as e:
            print(f"Błąd w pętli: {e}")
            
        await asyncio.sleep(INTERWAL_SPRAWDZANIA_SEKUNDY)

if __name__ == '__main__':
    asyncio.run(main())
