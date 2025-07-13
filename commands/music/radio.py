import os
import time
import discord
import random
import ffmpeg
import shutil
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from conf import embeds

class MusicBot():
    def __init__(self, bot : commands.Bot):
        self.bot = bot
        self.voice_clients = {}
        self.ffmpeg_path = os.getenv("FFMPEG_PATH")
        self.channel = None
        load_dotenv()

    async def new_song_generator(self):
        sub_folder = random.choice(os.listdir(os.getenv("RADIO_FOLDER")))
        if sub_folder == ".DS_Store": await self.new_song_generator()
        self.music = random.choice(os.listdir(os.getenv("RADIO_FOLDER")+"/"+sub_folder))
        self.music_path = os.getenv("RADIO_FOLDER") + "/" + sub_folder + "/" + self.music
        try: os.remove(os.getenv("RADIO_CURRENT_MUSIC")) 
        except: pass
        time.sleep(1)
        shutil.copy(self.music_path, os.getenv("RADIO_CURRENT_MUSIC"))
        msg = await self.bot.get_channel(int(os.getenv("RADIO_TRACKLIST_ID"))).send(
            embed=embeds.CURRENTLY_PLAYING_ON_RADIO(
                title=self.extract_between_dots(self.music),
                folder=sub_folder,            )
        )
        #await msg.add_reaction("💜")  # Replace with your sticker ID
    
    
    def extract_between_dots(self, s):
        first_dot = s.find(".")
        last_dot = s.rfind(".")
        
        if first_dot == -1 or last_dot == -1 or first_dot == last_dot:
            return ""  # Not enough dots to extract in-between content

    
        return s[first_dot + 1:last_dot]
    
    def after_playing(self, error):
        asyncio.run_coroutine_threadsafe(self.play_music(), self.bot.loop)

    async def start_radio(self):
        if self.channel:
            if not self.voice_clients.get(self.channel.id):
                try: 
                    await self.channel.connect()
                except: pass
                try:
                    voice_client.stop()
                except: pass
            voice_client : discord.VoiceClient = self.channel.guild.voice_client
            self.voice_clients[self.channel.id] = voice_client
            self.current_track = await self.new_song_generator()
            voice_client.play(discord.FFmpegOpusAudio(executable=self.ffmpeg_path, source=self.music_path), after=self.after_playing)
        else:
            voice_client = self.voice_clients[self.channel.id]
            if voice_client.is_playing(): voice_client.stop()
            await self.new_song_generator()
            voice_client.play(discord.FFmpegOpusAudio(executable=self.ffmpeg_path, source=self.music_path), after=self.after_playing)
        await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=self.extract_between_dots(self.music)))

    async def stop_radio(self):
        if self.channel:
            voice_client = self.voice_clients.get(self.channel.id)
            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
                del self.voice_clients[self.channel.id]
                await self.bot.change_presence(activity=None)
                try: os.remove(os.getenv("RADIO_CURRENT_MUSIC"))
                except: pass
        else:
            await self.bot.change_presence(activity=None)