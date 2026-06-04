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

# 1. Telegram konfiguracja 
TELEGRAM_BOT_TOKEN = '8834803275:AAGcWnR8ujcknQJ2hM_n0vwn2veM22OTnBs'
TELEGRAM_CHAT_ID = '8277719275' 

# 2. Kryteria wyszukiwania
MAX_CENA_GWH_WARM = 1200 # Maksymalna cena Gesamtmiete w Euro (dla GWH)
MAX_CENA_NHW_KALT = 1000 # Maksymalna cena Nettokaltmiete w Euro (dla NHW)
MIN_POKOJE = 2        # Minimalna liczba pokoi
MIN_METRAZ = 50       # Minimalny metraż w m2
DZIELNICE = ["Sachsenhausen-Nord", "Sachsenhausen-Süd", "Sachsenhausen", "Niederrad"] 

# 3. Parametry działania
INTERWAL_SPRAWDZANIA_SEKUNDY = 60 # Co ile sekund sprawdzać
PLIK_HISTORII = 'znalezione_mieszkania.json' 
RAPORT_CO_ILE_GODZIN = 24 # Co ile godzin bot ma meldować, że wciąż działa

# ==========================================
bot = Bot(token=TELEGRAM_BOT_TOKEN)

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot dziala w tle! Szukam mieszkan we Frankfurcie.")

def run_server():
    port = int(os.environ.get("PORT", 10000))
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
    if not DZIELNICE:
        return True
    tekst_lower = tekst.lower()
    return any(dzielnica.lower() in tekst_lower for dzielnica in DZIELNICE)

async def wyslij_powiadomienie(tytul, link, cena, pokoje, metraz, zrodlo):
    wiadomosc = (
        f"🚨 <b>NOWE MIESZKANIE! ({zrodlo})</b> 🚨\n\n"
        f"<b>Tytuł:</b> {tytul}\n"
        f"<b>Cena:</b> {cena} €\n"
        f"<b>Pokoje:</b> {pokoje}\n"
        f"<b>Metraż:</b> {metraz} m²\n\n"
        f"👉 <a href='{link}'>Zobacz ofertę</a>"
    )
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=wiadomosc, parse_mode='HTML')
    except Exception as e:
        print(f"Błąd wysyłania: {e}")

async def wyslij_raport_stanu():
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, 
            text="✅ <b>Raport Statusu:</b> Bot na serwerze RENDER nadal działa i monitoruje mieszkania!", 
            parse_mode='HTML'
        )
    except Exception:
        pass

def sprawdz_gwh():
    nowe_oferty = []
    # Używamy bardziej ogólnego adresu, który GWH serwuje dla wszystkich
    url_gwh = "https://www.gwh.de/mietangebote" 
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        # Pobieramy stronę i szukamy elementów kart ogłoszeń
        response = requests.get(url_gwh, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        # GWH często używa klas .estate-item lub podobnych w listach
        oferty = soup.select('.estate-item, .item, .teaser')
        
        znalezione_linki = set()
        for oferta in oferty:
            tekst = oferta.get_text(separator=' ', strip=True)
            link_tag = oferta.find('a', href=True)
            if not link_tag: continue
            
            link = "https://www.gwh.de" + link_tag['href']
            if link in znalezione_linki: continue
            
            cena_match = re.search(r'([\d\.,]+)\s*€', tekst)
            pokoje_match = re.search(r'([\d\.,]+)\s*(?:Zi|Zimmer)', tekst, re.IGNORECASE)
            metraz_match = re.search(r'([\d\.,]+)\s*m²', tekst)
            
            if cena_match and pokoje_match and metraz_match:
                try:
                    cena = float(cena_match.group(1).replace('.', '').replace(',', '.'))
                    pokoje = float(pokoje_match.group(1).replace(',', '.'))
                    metraz = float(metraz_match.group(1).replace(',', '.'))
                    if cena <= MAX_CENA_GWH_WARM and pokoje >= MIN_POKOJE and metraz >= MIN_METRAZ:
                        if not czy_pasuje_dzielnica(tekst): continue
                        znalezione_linki.add(link)
                        nowe_oferty.append({'id': f"gwh_{link[-10:]}", 'tytul': "Mieszkanie GWH", 'link': link, 'cena': cena, 'pokoje': pokoje, 'metraz': metraz, 'zrodlo': 'GWH'})
                except: continue
        return nowe_oferty
    except Exception as e:
        print(f"Błąd GWH: {e}")
        return []

def sprawdz_nhw():
    nowe_oferty = []
    url_nhw = "https://www.nhw.de/wohnungsangebote"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url_nhw, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        linki_ofert = soup.find_all('a', href=re.compile(r'/zuhause-finden/immobilie/'))
        znalezione_linki = set()
        for link_tag in linki_ofert:
            link = "https://www.nhw.de" + link_tag['href']
            if link in znalezione_linki: continue
            kontener = link_tag.find_parent('div') or link_tag
            tekst = kontener.get_text(separator=' ', strip=True)
            cena_match = re.search(r'([\d\.,]+)\s*€', tekst)
            pokoje_match = re.search(r'([\d\.,]+)\s*Zimmer', tekst, re.IGNORECASE)
            metraz_match = re.search(r'([\d\.,]+)\s*m²', tekst)
            if cena_match and pokoje_match and metraz_match:
                try:
                    cena = float(cena_match.group(1).replace('.', '').replace(',', '.'))
                    pokoje = float(pokoje_match.group(1).replace(',', '.'))
                    metraz = float(metraz_match.group(1).replace(',', '.'))
                    if cena <= MAX_CENA_NHW_KALT and pokoje >= MIN_POKOJE and metraz >= MIN_METRAZ:
                        if not czy_pasuje_dzielnica(tekst): continue
                        znalezione_linki.add(link)
                        nowe_oferty.append({'id': f"nhw_{link[-10:]}", 'tytul': "Mieszkanie NHW", 'link': link, 'cena': cena, 'pokoje': pokoje, 'metraz': metraz, 'zrodlo': 'NHW'})
                except: continue
        return nowe_oferty
    except Exception as e:
        print(f"Błąd NHW: {e}")
        return []

async def main():
    threading.Thread(target=run_server, daemon=True).start()
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 <b>Bot zaktualizowany i działa!</b>", parse_mode='HTML')
    czas_ostatniego_raportu = datetime.now()
    while True:
        try:
            historia = wczytaj_historie()
            wszystkie_znalezione = sprawdz_gwh() + sprawdz_nhw()
            nowe = [o for o in wszystkie_znalezione if o['id'] not in historia]
            if nowe:
                for oferta in nowe:
                    await wyslij_powiadomienie(oferta['tytul'], oferta['link'], oferta['cena'], oferta['pokoje'], oferta['metraz'], oferta['zrodlo'])
                    historia.append(oferta['id'])
                zapisz_historie(historia)
            if datetime.now() - czas_ostatniego_raportu > timedelta(hours=RAPORT_CO_ILE_GODZIN):
                await wyslij_raport_stanu()
                czas_ostatniego_raportu = datetime.now()
        except Exception as e:
            print(f"Błąd główny: {e}")
        await asyncio.sleep(INTERWAL_SPRAWDZANIA_SEKUNDY)

if __name__ == '__main__':
    asyncio.run(main())
