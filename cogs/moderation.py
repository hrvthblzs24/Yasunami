from __future__ import annotations

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core.access import require
from core.checks import ack
from core.database import Database
from core.defaults import MOD
from core.textfmt import fill


def _label(user: discord.abc.User) -> str:
    return f"{user.mention} (`{user}`)"


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Database = bot.db

    async def _cfg(self, guild_id: int, key: str):
        stored = await self.db.get_setting(guild_id, f"mod.{key}", None)
        if stored is None:
            return MOD.get(key)
        return stored

    async def _enabled(self, interaction: discord.Interaction, feature: str) -> bool:
        assert interaction.guild is not None
        on = await self._cfg(interaction.guild.id, f"{feature}.enabled")
        if on is False:
            await ack(interaction, f"**/{feature}** is disabled for this server.")
            return False
        return True

    async def _reply(self, interaction: discord.Interaction, key: str, **kwargs: object) -> None:
        assert interaction.guild is not None
        template = await self._cfg(interaction.guild.id, key)
        await ack(interaction, fill(str(template or "Done."), **kwargs), ephemeral=False)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Who to ban", reason="Shown in audit log and the reply", delete_days="Delete recent messages, 0–7")
    @app_commands.guild_only()
    @require("ban")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_days: app_commands.Range[int, 0, 7] = 0) -> None:
        if not await self._enabled(interaction, "ban"):
            return
        guild = interaction.guild
        assert guild is not None
        try:
            await guild.ban(member, reason=reason, delete_message_days=delete_days)
        except discord.Forbidden:
            await ack(interaction, "I cannot ban that member. Move my role higher.")
            return
        except discord.HTTPException as exc:
            await ack(interaction, f"Ban failed: {exc}")
            return
        await self._reply(interaction, "ban.response", user=_label(member), reason=reason)

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Who to kick", reason="Shown in audit log and the reply")
    @app_commands.guild_only()
    @require("kick")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided") -> None:
        if not await self._enabled(interaction, "kick"):
            return
        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            await ack(interaction, "I cannot kick that member. Move my role higher.")
            return
        except discord.HTTPException as exc:
            await ack(interaction, f"Kick failed: {exc}")
            return
        await self._reply(interaction, "kick.response", user=_label(member), reason=reason)

    @app_commands.command(name="mute", description="Timeout a member")
    @app_commands.describe(member="Who to mute", minutes="How long", reason="Shown in the reply")
    @app_commands.guild_only()
    @require("mute")
    async def mute(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320] | None = None, reason: str = "No reason provided") -> None:
        if not await self._enabled(interaction, "mute"):
            return
        assert interaction.guild is not None
        if minutes is None:
            stored = await self._cfg(interaction.guild.id, "mute.minutes")
            minutes = int(stored or 10)
        try:
            await member.timeout(timedelta(minutes=int(minutes)), reason=reason)
        except discord.Forbidden:
            await ack(interaction, "I cannot mute that member. Move my role higher.")
            return
        except discord.HTTPException as exc:
            await ack(interaction, f"Mute failed: {exc}")
            return
        await self._reply(interaction, "mute.response", user=_label(member), reason=reason, minutes=minutes)

    @app_commands.command(name="unmute", description="Remove a member timeout")
    @app_commands.describe(member="Who to unmute")
    @app_commands.guild_only()
    @require("mute")
    async def unmute(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await self._enabled(interaction, "mute"):
            return
        try:
            await member.timeout(None, reason="Unmute")
        except discord.Forbidden:
            await ack(interaction, "I cannot unmute that member.")
            return
        except discord.HTTPException as exc:
            await ack(interaction, f"Unmute failed: {exc}")
            return
        await self._reply(interaction, "unmute.response", user=_label(member), reason="Unmute")

    @app_commands.command(name="deaf", description="Server-deafen a member in voice")
    @app_commands.describe(member="Who to deafen", reason="Shown in the reply")
    @app_commands.guild_only()
    @require("deaf")
    async def deaf(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided") -> None:
        if not await self._enabled(interaction, "deaf"):
            return
        if member.voice is None:
            await ack(interaction, "That member is not in a voice channel.")
            return
        try:
            await member.edit(deafen=True, reason=reason)
        except discord.Forbidden:
            await ack(interaction, "I cannot deafen that member.")
            return
        except discord.HTTPException as exc:
            await ack(interaction, f"Deafen failed: {exc}")
            return
        await self._reply(interaction, "deaf.response", user=_label(member), reason=reason)

    @app_commands.command(name="undeaf", description="Remove server deafen")
    @app_commands.describe(member="Who to undeafen")
    @app_commands.guild_only()
    @require("deaf")
    async def undeaf(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await self._enabled(interaction, "deaf"):
            return
        try:
            await member.edit(deafen=False, reason="Undeafen")
        except discord.Forbidden:
            await ack(interaction, "I cannot undeafen that member.")
            return
        except discord.HTTPException as exc:
            await ack(interaction, f"Undeafen failed: {exc}")
            return
        await self._reply(interaction, "undeaf.response", user=_label(member), reason="Undeafen")

    @app_commands.command(name="msg", description="Send a message as Yasunami")
    @app_commands.describe(text="What to send", channel="Text channel (omit to use this one)", user="DM this user instead")
    @app_commands.guild_only()
    @require("msg")
    async def msg(self, interaction: discord.Interaction, text: str, channel: discord.TextChannel | None = None, user: discord.User | None = None) -> None:
        if not await self._enabled(interaction, "msg"):
            return
        try:
            if user is not None:
                await user.send(text)
                target = f"DM {_label(user)}"
            else:
                dest = channel or interaction.channel
                if dest is None or not hasattr(dest, "send"):
                    await ack(interaction, "Pick a text channel.")
                    return
                await dest.send(text)
                target = dest.mention if hasattr(dest, "mention") else str(dest)
        except discord.Forbidden:
            await ack(interaction, "I cannot send that message.")
            return
        except discord.HTTPException as exc:
            await ack(interaction, f"Send failed: {exc}")
            return
        await self._reply(interaction, "msg.response", target=target, reason=text, user=target)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
