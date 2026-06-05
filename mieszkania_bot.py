import requests
from bs4 import BeautifulSoup
import json
import os
import asyncio
import re
from telegram import Bot
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# Konfiguracja
TELEGRAM_BOT_TOKEN = '8834803275:AAGcWnR8ujcknQJ2hM_n0vwn2veM22OTnBs'
TELEGRAM_CHAT_ID = '8277719275' 
DZIELNICE = ["Sachsenhausen", "Niederrad"] 
INTERWAL = 60 
PLIK_HISTORII = 'znalezione.json'

bot = Bot(token=TELEGRAM_BOT_TOKEN)
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36'}

def wczytaj_historie():
    if os.path.exists(PLIK_HISTORII):
        with open(PLIK_HISTORII, 'r') as f: return json.load(f)
    return []

def zapisz_historie(historia):
    with open(PLIK_HISTORII, 'w') as f: json.dump(historia, f)

def czy_pasuje(tekst):
    return any(d.lower() in tekst.lower() for d in DZIELNICE)

def sprawdz_gwh():
    try:
        url = "https://www.gwh.de/mietangebote"
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        oferty = soup.select('.estate-item, .item, .teaser')
        wyniki = []
        for o in oferty:
            if czy_pasuje(o.get_text()):
                link = "https://www.gwh.de" + o.find('a')['href']
                wyniki.append({'id': link, 'zrodlo': 'GWH', 'link': link})
        return wyniki
    except: return []

def sprawdz_nhw():
    try:
        url = "https://www.nhw.de/wohnungsangebote"
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        linki = soup.find_all('a', href=re.compile(r'/zuhause-finden/immobilie/'))
        wyniki = []
        for l in linki:
            if czy_pasuje(l.find_parent('div').get_text()):
                link = "https://www.nhw.de" + l['href']
                wyniki.append({'id': link, 'zrodlo': 'NHW', 'link': link})
        return wyniki
    except: return []

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
        
    def log_message(self, format, *args):
        return  # Wyciszenie logów zapytań HTTP

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthCheckHandler).serve_forever()

async def monitoruj():
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🤖 Bot mieszkaniowy uruchomiony!")
    except: pass
    
    print("--- Bot aktywny i monitoruje co minutę ---")
    historia = wczytaj_historie()
    
    while True:
        try:
            print("--- Sprawdzam oferty (logi w tle)... ---")
            nowe_oferty = sprawdz_gwh() + sprawdz_nhw()
            znaleziono_nowe = False
            for oferta in nowe_oferty:
                if oferta['id'] not in historia:
                    msg = f"🚨 <b>Nowe mieszkanie! ({oferta['zrodlo']})</b>\n👉 <a href='{oferta['link']}'>Zobacz ofertę</a>"
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='HTML')
                    historia.append(oferta['id'])
                    znaleziono_nowe = True
            
            if znaleziono_nowe:
                zapisz_historie(historia)
            else:
                print("Brak nowych ofert.")
            
            await asyncio.sleep(INTERWAL)
        except Exception as e:
            print(f"Błąd: {e}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    threading.Thread(target=run_http_server, daemon=True).start()
    asyncio.run(monitoruj())
