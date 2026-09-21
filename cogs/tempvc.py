from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from core.database import Database
from core.utils import bot_has_voice_setup_perms, format_room_name, owner_overwrite

log = logging.getLogger("bot.tempvc")


class TempVoice(commands.Cog):
    """Join-to-create temporary voice channels (SQLite-backed)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Database = bot.db
        self._locks: dict[int, asyncio.Lock] = {}
        self._pending_delete: dict[int, asyncio.Task] = {}
        self._creating: set[int] = set()

    def _lock(self, guild_id: int) -> asyncio.Lock:
        lock = self._locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[guild_id] = lock
        return lock

    def _cancel_delete(self, channel_id: int) -> None:
        task = self._pending_delete.pop(channel_id, None)
        if task and not task.done():
            task.cancel()

    async def _delete_later(self, channel: discord.VoiceChannel, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            fresh = channel.guild.get_channel(channel.id)
            if fresh is None or not isinstance(fresh, discord.VoiceChannel):
                await self.db.unregister_room(channel.guild.id, channel.id)
                return
            if fresh.members:
                return
            await fresh.delete(reason="Temporary voice channel empty")
            await self.db.unregister_room(channel.guild.id, channel.id)
            log.info("Deleted empty temp VC %s in %s", fresh.name, channel.guild.name)
        except asyncio.CancelledError:
            return
        except discord.HTTPException as exc:
            log.warning("Failed to delete temp VC %s: %s", channel.id, exc)
        finally:
            self._pending_delete.pop(channel.id, None)

    async def _create_room(
        self,
        member: discord.Member,
        lobby: discord.VoiceChannel,
        category: discord.CategoryChannel | None,
        cfg: dict,
    ) -> discord.VoiceChannel | None:
        name = format_room_name(cfg["channel_name"], member)
        bitrate = int(cfg.get("bitrate") or lobby.bitrate or 64000)
        bitrate = max(8000, min(bitrate, member.guild.bitrate_limit))
        user_limit = int(cfg.get("user_limit") or 0)

        overwrites = dict(category.overwrites) if category is not None else {}
        overwrites[member] = owner_overwrite(member, cfg.get("owner_permissions") or [])
        if member.guild.me:
            overwrites[member.guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                manage_channels=True,
                move_members=True,
                manage_roles=True,
            )

        try:
            room = await member.guild.create_voice_channel(
                name=name,
                category=category,
                bitrate=bitrate,
                user_limit=user_limit,
                overwrites=overwrites,
                reason=f"Temp VC for {member} ({member.id})",
            )
        except discord.HTTPException as exc:
            log.exception("Could not create temp VC for %s: %s", member, exc)
            return None

        await self.db.register_room(
            member.guild.id,
            room.id,
            member.id,
            lobby.id,
            category.id if category else 0,
        )
        return room

    async def handle_join_lobby(self, member: discord.Member, lobby: discord.VoiceChannel) -> None:
        if member.id in self._creating:
            return
        cfg = await self.db.tempvc_config(member.guild.id)
        if not cfg.get("enabled", True):
            return

        entry = await self.db.lobby_entry(member.guild.id, lobby.id)
        if entry is None:
            return

        async with self._lock(member.guild.id):
            if cfg.get("one_room_per_owner"):
                existing = await self.db.owner_room(member.guild.id, member.id)
                if existing:
                    channel = member.guild.get_channel(int(existing["channel_id"]))
                    if isinstance(channel, discord.VoiceChannel):
                        self._cancel_delete(channel.id)
                        try:
                            await member.move_to(channel, reason="Existing temp VC")
                        except discord.HTTPException:
                            pass
                        return
                    await self.db.unregister_room(member.guild.id, int(existing["channel_id"]))

            category = None
            cat_id = int(entry["category_id"] or 0)
            if cat_id:
                fetched = member.guild.get_channel(cat_id)
                if isinstance(fetched, discord.CategoryChannel):
                    category = fetched
            if category is None:
                category = lobby.category

            missing = bot_has_voice_setup_perms(member.guild, category)
            if missing:
                log.error(
                    "Missing permissions in %s / %s: %s",
                    member.guild.name,
                    category,
                    ", ".join(missing),
                )
                return

            self._creating.add(member.id)
            try:
                room = await self._create_room(member, lobby, category, cfg)
                if room is None:
                    return
                try:
                    await member.move_to(room, reason="Created temp VC")
                except discord.HTTPException as exc:
                    log.warning("Created room but failed to move %s: %s", member, exc)
                    if not room.members:
                        await self._schedule_delete(room, cfg)
            finally:
                self._creating.discard(member.id)

    async def _schedule_delete(self, channel: discord.VoiceChannel, cfg: dict | None = None) -> None:
        cfg = cfg or await self.db.tempvc_config(channel.guild.id)
        delay = float(cfg.get("delete_delay_seconds") or 0)
        self._cancel_delete(channel.id)
        self._pending_delete[channel.id] = asyncio.create_task(self._delete_later(channel, delay))

    async def handle_leave_room(self, channel: discord.VoiceChannel) -> None:
        if await self.db.room(channel.guild.id, channel.id) is None:
            return
        if channel.members:
            self._cancel_delete(channel.id)
            return
        await self._schedule_delete(channel)

    async def cleanup_stale(self, guild: discord.Guild) -> None:
        for row in await self.db.rooms(guild.id):
            channel = guild.get_channel(int(row["channel_id"]))
            if not isinstance(channel, discord.VoiceChannel):
                await self.db.unregister_room(guild.id, int(row["channel_id"]))
                continue
            if not channel.members:
                await self._schedule_delete(channel)

        for row in await self.db.lobbies(guild.id):
            ch = guild.get_channel(int(row["lobby_id"]))
            if not isinstance(ch, discord.VoiceChannel):
                await self.db.remove_lobby(guild.id, int(row["lobby_id"]))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            try:
                await self.cleanup_stale(guild)
            except Exception:
                log.exception("Stale cleanup failed for %s", guild.id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.db.wipe_guild(guild.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if not isinstance(channel, discord.VoiceChannel):
            return
        if await self.db.room(channel.guild.id, channel.id):
            await self.db.unregister_room(channel.guild.id, channel.id)
            self._cancel_delete(channel.id)
        if channel.id in await self.db.lobby_ids(channel.guild.id):
            await self.db.remove_lobby(channel.guild.id, channel.id)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot or before.channel == after.channel:
            return

        guild = member.guild
        lobby_ids = await self.db.lobby_ids(guild.id)
        room_ids = await self.db.room_ids(guild.id)

        if after.channel and after.channel.id in lobby_ids:
            await self.handle_join_lobby(member, after.channel)

        if before.channel and before.channel.id in room_ids:
            current = guild.get_channel(before.channel.id)
            if isinstance(current, discord.VoiceChannel):
                await self.handle_leave_room(current)
            else:
                await self.db.unregister_room(guild.id, before.channel.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TempVoice(bot))
