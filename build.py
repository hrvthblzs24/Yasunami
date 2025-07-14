import discord
import os
import botconf
from dotenv import load_dotenv
from discord.ext import commands
from commands.music import radio
from commands.misc.gamepass import GamePassGames
from commands.psinfo.psgame import search_psgame
from psnawp_api import PSNAWP
from conf import embeds

load_dotenv()


INTENTS = discord.Intents.all()
YASUNAMI = botconf.BaseBot(command_prefix=os.getenv("PREFIX"), intents=INTENTS)
MUSICBOT = radio.MusicBot(YASUNAMI)
PSNAPI = PSNAWP(os.getenv("NPSSO"))
WEBHOOK = YASUNAMI.webhook
DATABASE = YASUNAMI.database
DB_CURSOR = YASUNAMI.database.cursor
GAMEPASSGAMES = GamePassGames(YASUNAMI, DATABASE, DB_CURSOR)



#PSINFO COMAMNDS
@YASUNAMI.command(name="psgame", descrition="Search for a PlayStation game.")
async def psgame(ctx : commands.Context, *query):
    await ctx.send(embed=await search_psgame(YASUNAMI, PSNAPI, query))

#RADIO COMMANDS
@YASUNAMI.command(name="startradio", description="Connect to the radio channel.")
async def startradio(ctx: commands.Context):
    await MUSICBOT.start_radio()
@YASUNAMI.command(name="stopradio", description="Disconnect from the radio channel.")
async def stopradio(ctx: commands.Context):
    await MUSICBOT.stop_radio()


#MISC COMMANDS
@YASUNAMI.command(name="whoismilox", description="Connect to the radio channel.")
async def whoismilox(ctx: commands.Context):
    await ctx.send(embed=embeds.GET_KNOWN_CARD(YASUNAMI))
@YASUNAMI.tree.command(name="ping", description="Check the bot's latency.", guild=discord.Object(id=1378740808274153532))
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! Latency: {round(YASUNAMI.latency * 1000)}ms")     

YASUNAMI.run(os.getenv("TOKEN"))