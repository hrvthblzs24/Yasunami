import discord
from discord.ext import commands
from webhook.main import WebhookInstance
from db.main import YasunamiDatabase
from commands.misc.gamepass import GamePassGames
import os
import pandas as pd

from dotenv import load_dotenv



class BaseBot(commands.Bot):
    def __init__(self, command_prefix, intents):
        load_dotenv()
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.webhook = WebhookInstance(["https://discord.com/api/webhooks/1394311423357882418/R-FP_KLvhMBCB1mIhQYyPQj1wtlGOyQ7U9_ke4_3smKj8VpHNP31Z7N6O9XXtdx3L2Ds","https://discord.com/api/webhooks/1394331151480389834/BYmo7ghT53mvgrPRORCaltTV0tX5nJXCszeM4_mk5b3i3ELgnFy7N3W7pI-X1AscSO_H"])
        self.database = YasunamiDatabase(os.getenv("DB_PATH"))
        self.gamepass = GamePassGames(self, self.database.db, self.database.cursor)
        self.remove_command('help')
    async def on_ready(self):
        print(f'Logged in as {self.user.name} - {self.user.id}')
        print('------')
        self.gamepass.fetch_games(self.webhook)
        await self.tree.sync(guild=discord.Object(id=int(os.getenv("MAIN_GUILD_ID"))))
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Érvénytelen parancs. Kérlek, ellenőrizd a parancs nevét.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Hiányzó kötelező argumentum. Kérlek, ellenőrizd a parancs használatát.")
        else:
            await ctx.send(f"Hiba: {error}")
    async def on_message(self, message : commands.Context):
        if message.author == self.user:
            return
        await self.process_commands(message)
      