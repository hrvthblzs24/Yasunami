import discord
import os
import botconf
from dotenv import load_dotenv
from discord.ext import commands
from commands.music import radio
from conf import embeds


INTENTS = discord.Intents.all()
YASUNAMI = botconf.BaseBot(command_prefix=os.getenv("PREFIX"), intents=INTENTS)
MUSICBOT = radio.MusicBot(YASUNAMI)

@YASUNAMI.command(name="startradio", description="Connect to the radio channel.")
async def startradio(ctx: commands.Context):
    await MUSICBOT.start_radio()

@YASUNAMI.command(name="stopradio", description="Disconnect from the radio channel.")
async def stopradio(ctx: commands.Context):
    await MUSICBOT.stop_radio()

@YASUNAMI.command(name="whoismilox", description="Connect to the radio channel.")
async def whoismilox(ctx: commands.Context):
    await ctx.send(embed=embeds.GET_KNOWN_CARD(YASUNAMI))

@YASUNAMI.tree.command(name="ping", description="Check the bot's latency.", guild=discord.Object(id=1378740808274153532))
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! Latency: {round(YASUNAMI.latency * 1000)}ms")     

YASUNAMI.run(load_dotenv() and os.getenv("TOKEN"))