import discord
from discord.ext import commands
import os
import pandas as pd
from dotenv import load_dotenv



class BaseBot(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.claim_channels = pd.read_csv(os.getenv("CLAIM_SERVER_LIST"), sep=",", header=None)[0].tolist()
        self.override_accounts = pd.read_csv(os.getenv("OVERRIDE_ACCOUNTS"), sep=",", header=None)[0].tolist()

        print(self.claim_channels)
        self.remove_command('help')
        load_dotenv()

    async def on_ready(self):
        print(f'Logged in as {self.user.name} - {self.user.id}')
        print('------')
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
        if message.author.id not in self.override_accounts:
            if message.channel.id in self.claim_channels:
                await message.delete()


        await self.process_commands(message)