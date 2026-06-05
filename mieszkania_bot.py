import requests
from bs4 import BeautifulSoup
import json
import os
import asyncio
import re
from telegram import Bot
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# Konfiguracja
TELEGRAM_BOT_TOKEN = '8834803275:AAGcWnR8ujcknQJ2hM_n0vwn2veM22OTnBs'
TELEGRAM_CHAT_ID = '8277719275' 
MAX_CENA_GWH_WARM = 1200 
MAX_CENA_NHW_KALT = 1000 
# Uproszczona lista dzielnic
DZIELNICE = ["Sachsenhausen", "Niederrad"] 
INTERWAL = 60 

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Nagłówki udające przeglądarkę
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}

def sprawdz_gwh():
    try:
        url = "https://www.gwh.de/mietangebote"
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        oferty = soup.select('.estate-item, .item, .teaser')
        return len(oferty)
    except: return -1

def sprawdz_nhw():
    try:
        url = "https://www.nhw.de/wohnungsangebote"
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        oferty = soup.find_all('a', href=re.compile(r'/zuhause-finden/immobilie/'))
        return len(oferty)
    except: return -1

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

async def monitoruj():
    print("--- Rozpoczynam monitorowanie... ---")
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ Bot aktywny! Monitoruję: Sachsenhausen, Niederrad.", parse_mode='HTML')
    
    while True:
        try:
            print("--- Sprawdzam oferty... ---")
            gwh = sprawdz_gwh()
            nhw = sprawdz_nhw()
            print(f"Status: GWH={gwh}, NHW={nhw}")
            
            # Powiadomienie na Telegramie
            msg = f"🔍 <b>Status sprawdzania:</b>\n- GWH: {gwh} znalezionych\n- NHW: {nhw} znalezionych"
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='HTML')
            
            await asyncio.sleep(INTERWAL)
        except Exception as e:
            print(f"Błąd pętli: {e}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    threading.Thread(target=run_http_server, daemon=True).start()
    asyncio.run(monitoruj())
