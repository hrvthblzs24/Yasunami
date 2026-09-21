from __future__ import annotations

import asyncio
import logging

import discord

log = logging.getLogger("yasunami.musicbot")


class MusicBot(discord.Client):
    """Second Discord application that only joins voice and plays audio."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        super().__init__(intents=intents)
        self.ready_event = asyncio.Event()

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Music bot online as %s (%s)", self.user, self.user.id)
        self.ready_event.set()
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name="Yasunami")
        )


async def start_music_bot(token: str) -> MusicBot:
    client = MusicBot()
    asyncio.get_running_loop().create_task(client.start(token), name="yasunami-music-bot")
    try:
        await asyncio.wait_for(client.ready_event.wait(), timeout=25)
    except asyncio.TimeoutError:
        log.error("Music bot did not become ready in time. Check MUSIC_TOKEN and the invite.")
    return client
