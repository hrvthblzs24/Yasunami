from __future__ import annotations

import logging
import os
from pathlib import Path

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from core.database import Database
from core.music_bot import start_music_bot
from core.reloader import HotReloader
from web.app import start_dashboard

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("yasunami")

EXTENSIONS = (
    "cogs.tempvc",
    "cogs.commands",
    "cogs.welcome",
    "cogs.rules",
    "cogs.profile",
    "cogs.rps",
    "cogs.moderation",
    "cogs.music",
)

HEARTS = ("🩷", "🧠", "🧠", "💛", "💚", "💙", "💜", "❤️")


class Yasunami(commands.Bot):
    """Yasunami — all-in-one Discord bot by MILOX."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.members = os.getenv("MEMBERS_INTENT", "true").lower() in {"1", "true", "yes"}
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.db = Database()
        self.dashboard = None
        self.music_bot = None
        self._reloader: HotReloader | None = None
        self._heart_index = 0

    def _presence_activity(self) -> discord.BaseActivity:
        heart = HEARTS[self._heart_index % len(HEARTS)]
        name = f"Made by ❀𝕞𝕚𝕝𝕠𝕩, with {heart}"
        return discord.CustomActivity(name=name)

    @tasks.loop(seconds=10)
    async def rotate_presence(self) -> None:
        self._heart_index = (self._heart_index + 1) % len(HEARTS)
        try:
            await self.change_presence(activity=self._presence_activity())
        except discord.HTTPException:
            log.debug("Presence update skipped")

    @rotate_presence.before_loop
    async def before_rotate_presence(self) -> None:
        await self.wait_until_ready()

    async def setup_hook(self) -> None:
        await self.db.connect()
        log.info("Yasunami SQLite ready at %s", self.db.path)
        for ext in EXTENSIONS:
            await self.load_extension(ext)
            log.info("Loaded %s", ext)

        music_token = (os.getenv("MUSIC_TOKEN") or "").strip()
        if music_token and music_token != "your_music_bot_token_here":
            try:
                self.music_bot = await start_music_bot(music_token)
            except Exception:
                log.exception("Music bot failed to start")
        else:
            log.warning("MUSIC_TOKEN is not set — /play will not join a voice channel")

        if os.getenv("DASHBOARD", "true").lower() in {"1", "true", "yes"}:
            self.dashboard = await start_dashboard(self)

        if os.getenv("HOT_RELOAD", "true").lower() in {"1", "true", "yes"}:
            self._reloader = HotReloader(self)
            self._reloader.start()

        if not self.rotate_presence.is_running():
            self.rotate_presence.start()

        dev = (os.getenv("DEV_GUILD_ID") or "").strip()
        try:
            if dev:
                guild = discord.Object(id=int(dev))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info("Synced %s guild commands to %s", len(synced), dev)
            else:
                synced = await self.tree.sync()
                log.info("Synced %s global commands", len(synced))
        except discord.Forbidden:
            log.error(
                "Slash command sync got 50001 Missing Access. "
                "Kick Yasunami and re-invite with BOTH scopes: "
                "bot AND applications.commands. "
                "If DEV_GUILD_ID is set, it must be a server the bot is already in."
            )
        except Exception:
            log.exception("Slash command sync failed")

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Yasunami online as %s (%s)", self.user, self.user.id)
        await self.change_presence(activity=self._presence_activity())

    async def close(self) -> None:
        if self.rotate_presence.is_running():
            self.rotate_presence.cancel()
        if self._reloader:
            self._reloader.stop()
        if self.dashboard is not None:
            await self.dashboard.stop()
        if self.music_bot is not None:
            await self.music_bot.close()
        await self.db.close()
        await super().close()


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token or token == "your_bot_token_here":
        raise SystemExit("Set DISCORD_TOKEN in a .env file (see .env.example).")
    Yasunami().run(token, log_handler=None)


if __name__ == "__main__":
    main()
