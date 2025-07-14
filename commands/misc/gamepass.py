import requests
from discord import Color

from webhook.main import WebhookInstance
from discord.ext import commands
from conf.embeds import NEW_GAMEPASS_GAME

import sqlite3

class GamePassGames:
    def __init__(self, bot : commands.Bot, db : sqlite3.Connection, cursor : sqlite3.Cursor):
        self.bot = bot
        self.titles = []
        self.db = db
        self.cursor = cursor
        self.missing_counter = 0
    
    def send_alert(self, title : str, webhook : WebhookInstance):
        self.webhook = webhook
        self.webhook.add_embed(title, "🎮| Új játék az Xbox GamePass katalógusán!", "0x2ECC71")
        self.webhook.start_sending()
    
    
    def fetch_games(self, webhook : WebhookInstance):
        sigls_url = "https://catalog.gamepass.com/sigls/v2?id=29a81209-df6f-41fd-a528-2ae6b91f719c&language=en-us&market=US"
        response = requests.get(sigls_url)
        response.raise_for_status()
        data = response.json()
        ids = [item['id'] for item in data if 'id' in item]
        ids_str = ",".join(ids)
        
        products_url = f"https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds={ids_str}&market=US&languages=en-us&MS-CV=DGU1mcuYo0WMMp"
        products_response = requests.get(products_url)
        products_response.raise_for_status()
        products_data = products_response.json()
        
        for product in products_data.get("Products", []):
            localized = product.get("LocalizedProperties", [])
            name = localized[0].get("ProductTitle")
            self.titles.append(name)
        for title in self.titles:
            q = self.cursor.execute('SELECT 1 FROM gamepass_games WHERE title = ?', (title,))
            result = q.fetchone()        
            if result is None:
                self.cursor.execute('INSERT INTO gamepass_games (title) VALUES (?)', (title,))
                self.missing_counter += 1
                self.send_alert(title, webhook)
        self.db.commit()
        self.db.close()

