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
    url_gwh = "https://www.gwh.de/mieten" 
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url_gwh, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        oferty_html = soup.find_all(['div', 'article', 'a'])
        znalezione_linki = set()
        surowe_oferty = 0
        for oferta in oferty_html:
            tekst = oferta.get_text(separator=' ', strip=True)
            if "Frankfurt" not in tekst: continue
            link_tag = oferta if oferta.name == 'a' else oferta.find('a')
            if not link_tag or not link_tag.has_attr('href'): continue
            link = link_tag['href']
            if not link.startswith('http'): link = "https://www.gwh.de" + link
            if link in znalezione_linki: continue
            cena_match = re.search(r'([\d\.,]+)\s*€', tekst)
            pokoje_match = re.search(r'([\d\.,]+)\s*Zimmer', tekst, re.IGNORECASE)
            metraz_match = re.search(r'([\d\.,]+)\s*m²', tekst)
            if cena_match and pokoje_match and metraz_match:
                surowe_oferty += 1
                try:
                    cena = float(cena_match.group(1).replace('.', '').replace(',', '.'))
                    pokoje = float(pokoje_match.group(1).replace(',', '.'))
                    metraz = float(metraz_match.group(1).replace(',', '.'))
                    id_oferty = link.split('/')[-1].split('?')[0][-10:]
                    if cena <= MAX_CENA_GWH_WARM and pokoje >= MIN_POKOJE and metraz >= MIN_METRAZ:
                        if not czy_pasuje_dzielnica(tekst): continue
                        znalezione_linki.add(link)
                        nowe_oferty.append({
                            'id': f"gwh_{id_oferty}", 'tytul': f"Mieszkanie GWH - {pokoje} pok.",
                            'link': link, 'cena': cena, 'pokoje': pokoje, 'metraz': metraz, 'zrodlo': 'GWH'
                        })
                except Exception: continue
        print(f"GWH: Znalazłem {surowe_oferty} ofert przed filtr. Po filtrach: {len(nowe_oferty)}")
        return nowe_oferty
    except Exception as e:
        print(f"Błąd GWH: {e}")
        return []

def sprawdz_nhw():
    nowe_oferty = []
    url_nhw = "https://www.nhw.de/mietwohnungen/frankfurt"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url_nhw, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        linki_ofert = soup.find_all('a', href=re.compile(r'/zuhause-finden/immobilie/'))
        znalezione_linki = set()
        surowe_oferty = 0
        for link_tag in linki_ofert:
            link = "https://www.nhw.de" + link_tag['href']
            if link in znalezione_linki: continue
            kontener = link_tag.find_parent('div') or link_tag
            tekst = kontener.get_text(separator=' ', strip=True)
            cena_match = re.search(r'([\d\.,]+)\s*€\s*Nettokaltmiete', tekst, re.IGNORECASE) or re.search(r'([\d\.,]+)\s*€', tekst)
            pokoje_match = re.search(r'([\d\.,]+)\s*Zimmer', tekst, re.IGNORECASE)
            metraz_match = re.search(r'([\d\.,]+)\s*m²', tekst)
            if cena_match and pokoje_match and metraz_match:
                surowe_oferty += 1
                try:
                    cena = float(cena_match.group(1).replace('.', '').replace(',', '.'))
                    pokoje = float(pokoje_match.group(1).replace(',', '.'))
                    metraz = float(metraz_match.group(1).replace(',', '.'))
                    id_oferty = link.split('/')[-1].split('?')[0][-10:]
                    if cena <= MAX_CENA_NHW_KALT and pokoje >= MIN_POKOJE and metraz >= MIN_METRAZ:
                        if not czy_pasuje_dzielnica(tekst): continue
                        znalezione_linki.add(link)
                        tytul_match = re.search(r'([^\.]+Frankfurt[^\.]+)', tekst)
                        tytul = tytul_match.group(1).strip() if tytul_match else f"Mieszkanie NHW"
                        nowe_oferty.append({
                            'id': f"nhw_{id_oferty}", 'tytul': tytul, 'link': link,
                            'cena': cena, 'pokoje': pokoje, 'metraz': metraz, 'zrodlo': 'NHW'
                        })
                except Exception: continue
        print(f"NHW: Znalazłem {surowe_oferty} ofert przed filtr. Po filtrach: {len(nowe_oferty)}")
        return nowe_oferty
    except Exception as e:
        print(f"Błąd NHW: {e}")
        return []

async def main():
    # Odpalamy niewidzialną stronę dla Render.com
    threading.Thread(target=run_server, daemon=True).start()
    
    print("\n" + "="*50)
    print("🤖 BOT MIESZKANIOWY URUCHOMIONY W CHMURZE RENDER!")
    print("="*50 + "\n")
    
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🚀 <b>Uruchomiono bota na serwerze!</b> Szukam mieszkań...", parse_mode='HTML')
    except Exception:
        pass

    czas_ostatniego_raportu = datetime.now()
    
    while True:
        try:
            historia = wczytaj_historie()
            oferty_gwh = sprawdz_gwh()
            oferty_nhw = sprawdz_nhw()
            
            wszystkie_znalezione = oferty_gwh + oferty_nhw
            nowe_do_wyslania = [o for o in wszystkie_znalezione if o['id'] not in historia]
            
            if nowe_do_wyslania:
                for oferta in nowe_do_wyslania:
                    await wyslij_powiadomienie(oferta['tytul'], oferta['link'], oferta['cena'], oferta['pokoje'], oferta['metraz'], oferta['zrodlo'])
                    historia.append(oferta['id'])
                    await asyncio.sleep(2)
                zapisz_historie(historia)
            
            if datetime.now() - czas_ostatniego_raportu > timedelta(hours=RAPORT_CO_ILE_GODZIN):
                await wyslij_raport_stanu()
                czas_ostatniego_raportu = datetime.now()
                
        except Exception as e:
            print(f"Błąd główny: {e}")
            
        await asyncio.sleep(INTERWAL_SPRAWDZANIA_SEKUNDY)

if __name__ == '__main__':
    asyncio.run(main())
