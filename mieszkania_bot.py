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

# Konfiguracja (pozostaje bez zmian)
TELEGRAM_BOT_TOKEN = '8834803275:AAGcWnR8ujcknQJ2hM_n0vwn2veM22OTnBs'
TELEGRAM_CHAT_ID = '8277719275' 
MAX_CENA_GWH_WARM = 1200 
MAX_CENA_NHW_KALT = 1000 
DZIELNICE = ["Sachsenhausen", "Niederrad"] 
INTERWAL = 60 

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Prosty serwer, który tylko odpowiada na "zdrowie"
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
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ Bot działa i monitoruje!", parse_mode='HTML')
    
    while True:
        try:
            print("--- Sprawdzam oferty... ---")
            # Tu wstawilibyśmy logikę sprawdzania (skrócona wersja dla testu)
            # Jeśli to przejdzie, dodamy resztę kodu
            await asyncio.sleep(INTERWAL)
        except Exception as e:
            print(f"Błąd pętli: {e}")
            await asyncio.sleep(10)

if __name__ == '__main__':
    threading.Thread(target=run_http_server, daemon=True).start()
    asyncio.run(monitoruj())
