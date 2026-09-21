from __future__ import annotations

import asyncio
import logging
from collections import deque

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import ack
from core.database import Database
from core.defaults import MUSIC

log = logging.getLogger("yasunami.music")

def _js_runtimes() -> dict[str, str | None]:
    import shutil

    found: dict[str, str | None] = {}
    for name in ("deno", "node", "qjs"):
        path = shutil.which(name)
        if path:
            key = "quickjs" if name == "qjs" else name
            found[key] = path
    if not found:
        found["deno"] = None
        found["node"] = None
    return found


YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "js_runtimes": _js_runtimes(),
}

FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class Track:
    def __init__(self, title: str, url: str, webpage: str, requester: str) -> None:
        self.title = title
        self.url = url
        self.webpage = webpage
        self.requester = requester


def _extract(query: str) -> Track:
    import yt_dlp

    with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if info is None:
            raise RuntimeError("No result")
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise RuntimeError("No result")
            info = entries[0]
        url = info.get("url") or info.get("webpage_url")
        title = info.get("title") or query
        page = info.get("webpage_url") or query
        return Track(title=title, url=url, webpage=page, requester="")


class GuildPlayer:
    def __init__(self, cog: Music, guild: discord.Guild) -> None:
        self.cog = cog
        self.guild = guild
        self.queue: deque[Track] = deque()
        self.history: deque[Track] = deque(maxlen=30)
        self.current: Track | None = None
        self.volume = 0.8

    def slave_guild(self) -> discord.Guild | None:
        mb = getattr(self.cog.bot, "music_bot", None)
        if mb is None or not getattr(mb, "is_ready", lambda: False)():
            return None
        return mb.get_guild(self.guild.id)

    def voice(self) -> discord.VoiceClient | None:
        guild = self.slave_guild()
        if guild is None:
            return None
        vc = guild.voice_client
        return vc if isinstance(vc, discord.VoiceClient) else None

    def snapshot(self) -> dict:
        return {
            "current": None if self.current is None else self.current.title,
            "queue": [t.title for t in self.queue],
            "paused": bool(self.voice() and self.voice().is_paused()),
            "connected": bool(self.voice()),
        }

    async def start(self) -> None:
        if self.current or not self.queue:
            return
        await self._play_next()

    async def _play_next(self) -> None:
        vc = self.voice()
        if vc is None or not self.queue:
            self.current = None
            return
        track = self.queue.popleft()
        self.current = track
        source = discord.FFmpegPCMAudio(track.url, **FFMPEG_OPTS)
        audio = discord.PCMVolumeTransformer(source, volume=self.volume)

        def after(err: Exception | None) -> None:
            if err:
                log.warning("Player error: %s", err)
            fut = asyncio.run_coroutine_threadsafe(self._after(), self.cog.bot.loop)
            try:
                fut.result()
            except Exception:
                log.exception("after() failed")

        vc.play(audio, after=after)
        if await self.cog.db.get_setting(self.guild.id, "music.announce", MUSIC["announce"]):
            channel = self.guild.system_channel
            if channel is not None:
                try:
                    await channel.send(f"Now playing **{track.title}** — requested by {track.requester}")
                except discord.HTTPException:
                    pass

    async def _after(self) -> None:
        if self.current:
            self.history.append(self.current)
        self.current = None
        await self._play_next()

    async def skip(self) -> str:
        vc = self.voice()
        if vc and vc.is_playing():
            vc.stop()
            return "Skipped."
        if self.queue:
            await self._play_next()
            return "Skipped."
        return "Nothing to skip."

    async def previous(self) -> str:
        if not self.history:
            return "No previous track."
        prev = self.history.pop()
        if self.current:
            self.queue.appendleft(self.current)
        self.queue.appendleft(prev)
        vc = self.voice()
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        else:
            await self._play_next()
        return f"Playing previous: **{prev.title}**"

    def pause(self) -> str:
        vc = self.voice()
        if vc is None:
            return "Not connected."
        if vc.is_playing():
            vc.pause()
            return "Paused."
        if vc.is_paused():
            vc.resume()
            return "Resumed."
        return "Nothing is playing."

    def resume(self) -> str:
        vc = self.voice()
        if vc and vc.is_paused():
            vc.resume()
            return "Resumed."
        return "Nothing is paused."

    async def stop(self) -> str:
        self.queue.clear()
        self.current = None
        vc = self.voice()
        if vc:
            vc.stop()
            await vc.disconnect()
        return "Stopped and left the channel."


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Database = bot.db
        self.players: dict[int, GuildPlayer] = {}

    def player(self, guild: discord.Guild) -> GuildPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = GuildPlayer(self, guild)
        return self.players[guild.id]

    async def _on(self, interaction: discord.Interaction) -> bool:
        assert interaction.guild is not None
        if await self.db.get_setting(interaction.guild.id, "music.enabled", True) is False:
            await ack(interaction, "Music is disabled on this server.")
            return False
        return True

    async def _ensure_voice(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        assert interaction.guild is not None
        member = interaction.user
        if not isinstance(member, discord.Member) or member.voice is None or member.voice.channel is None:
            await ack(interaction, "Join a voice channel first.")
            return None
        mb = getattr(self.bot, "music_bot", None)
        if mb is None or not mb.is_ready():
            await ack(interaction, "Music bot is offline. Set MUSIC_TOKEN and invite that bot with Connect + Speak.")
            return None
        slave = mb.get_guild(interaction.guild.id)
        if slave is None:
            await ack(interaction, "Invite the music bot to this server with Connect and Speak.")
            return None
        channel_id = member.voice.channel.id
        dest = slave.get_channel(channel_id)
        if dest is None:
            try:
                dest = await mb.fetch_channel(channel_id)
            except discord.Forbidden:
                await ack(interaction, "Music bot needs View Channel, Connect, and Speak on that voice channel.")
                return None
            except discord.NotFound:
                await ack(interaction, "That voice channel no longer exists.")
                return None
            except discord.HTTPException as exc:
                await ack(interaction, f"Music bot could not load that channel: {exc}")
                return None
        if dest is None or not hasattr(dest, "connect"):
            await ack(interaction, "Give the music bot View Channel + Connect + Speak on that channel.")
            return None
        vc = slave.voice_client
        try:
            if vc is None:
                return await dest.connect()
            if isinstance(vc, discord.VoiceClient) and vc.channel != dest:
                await vc.move_to(dest)
        except discord.Forbidden:
            await ack(interaction, "The music bot cannot Connect or Speak there.")
            return None
        except discord.ClientException as exc:
            await ack(interaction, f"Music bot could not join: {exc}")
            return None
        return vc if isinstance(vc, discord.VoiceClient) else slave.voice_client

    @app_commands.command(name="play", description="Play a song or add it to the queue")
    @app_commands.describe(query="YouTube URL or search")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        if not await self._on(interaction):
            return
        assert interaction.guild is not None
        await interaction.response.defer()
        if await self._ensure_voice(interaction) is None:
            return
        player = self.player(interaction.guild)
        limit = int(await self.db.get_setting(interaction.guild.id, "music.max_queue", MUSIC["max_queue"]) or 50)
        if len(player.queue) >= limit:
            await interaction.followup.send(f"Queue is full ({limit}).")
            return
        try:
            track = await asyncio.to_thread(_extract, query)
        except Exception as exc:
            await interaction.followup.send(
                "Could not load that track. YouTube needs a JS runtime now. "
                "Install Deno (irm https://deno.land/install.ps1 | iex), then pip install -U yt-dlp yt-dlp-ejs. "
                f"({exc})"
            )
            return
        track.requester = interaction.user.mention
        vol = await self.db.get_setting(interaction.guild.id, "music.volume", MUSIC["volume"])
        player.volume = max(0.05, min(1.5, int(vol or 80) / 100))
        player.queue.append(track)
        if player.current is None:
            await player.start()
            await interaction.followup.send(f"Playing **{track.title}**")
        else:
            await interaction.followup.send(f"Queued **{track.title}** (`{len(player.queue)}` in queue)")

    @app_commands.command(name="pause", description="Pause or resume playback")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        if not await self._on(interaction):
            return
        assert interaction.guild is not None
        await ack(interaction, self.player(interaction.guild).pause(), ephemeral=False)

    @app_commands.command(name="next", description="Skip to the next track")
    @app_commands.guild_only()
    async def next_track(self, interaction: discord.Interaction) -> None:
        if not await self._on(interaction):
            return
        assert interaction.guild is not None
        await ack(interaction, await self.player(interaction.guild).skip(), ephemeral=False)

    @app_commands.command(name="previous", description="Play the previous track")
    @app_commands.guild_only()
    async def previous(self, interaction: discord.Interaction) -> None:
        if not await self._on(interaction):
            return
        assert interaction.guild is not None
        await ack(interaction, await self.player(interaction.guild).previous(), ephemeral=False)

    @app_commands.command(name="stop", description="Stop playback and leave voice")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        if not await self._on(interaction):
            return
        assert interaction.guild is not None
        await ack(interaction, await self.player(interaction.guild).stop(), ephemeral=False)

    @app_commands.command(name="queue", description="Show the music queue")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        player = self.player(interaction.guild)
        if player.current is None and not player.queue:
            await ack(interaction, "Queue is empty.")
            return
        lines = []
        if player.current:
            lines.append(f"**Now:** {player.current.title}")
        for i, track in enumerate(player.queue, start=1):
            lines.append(f"`{i}.` {track.title}")
        await ack(interaction, "\n".join(lines) or "Queue is empty.", ephemeral=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
