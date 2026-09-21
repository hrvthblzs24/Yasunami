from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import is_admin
from core.database import Database
from core.defaults import WELCOME_DM, WELCOME_MESSAGE
from core.emojiutil import parse_emoji

log = logging.getLogger("bot.welcome")

DEFAULT_MESSAGE = WELCOME_MESSAGE
DEFAULT_DM = WELCOME_DM


def render(template: str, member: discord.Member, join_count: int) -> str:
    mapping = {
        "user": member.display_name,
        "name": member.name,
        "mention": member.mention,
        "server": member.guild.name,
        "guild": member.guild.name,
        "member_count": str(member.guild.member_count or 0),
        "join_count": str(join_count),
        "id": str(member.id),
    }

    def repl(match: re.Match[str]) -> str:
        return mapping.get(match.group(1), match.group(0))

    return re.sub(r"\{([a-zA-Z0-9_]+)\}", repl, template)[:2000]


class Welcome(commands.Cog):
    """Track joins in SQLite, post a welcome, react to it."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Database = bot.db

    async def _welcome_cfg(self, guild_id: int) -> dict:
        return {
            "enabled": await self.db.get_setting(guild_id, "welcome.enabled", True),
            "channel_id": await self.db.get_setting(guild_id, "welcome.channel_id", None),
            "message": await self.db.get_setting(guild_id, "welcome.message", DEFAULT_MESSAGE),
            "reactions": await self.db.get_setting(guild_id, "welcome.reactions", ["👋"]),
            "dm_enabled": await self.db.get_setting(guild_id, "welcome.dm_enabled", False),
            "dm_message": await self.db.get_setting(guild_id, "welcome.dm_message", DEFAULT_DM),
        }

    async def _add_reactions(self, message: discord.Message, raw_list: list) -> None:
        if not raw_list:
            return
        for raw in raw_list:
            if not raw:
                continue
            emoji = parse_emoji(str(raw))
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException as exc:
                log.warning("Could not react %s on %s: %s", raw, message.id, exc)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            await self.db.record_join(
                member.guild.id,
                member.id,
                member.name,
                member.global_name,
                member.joined_at,
            )
            return

        join_count = await self.db.record_join(
            member.guild.id,
            member.id,
            member.name,
            member.global_name,
            member.joined_at or datetime.now(timezone.utc),
        )
        cfg = await self._welcome_cfg(member.guild.id)
        if not cfg["enabled"]:
            return

        text = render(cfg["message"] or DEFAULT_MESSAGE, member, join_count)

        channel = None
        if cfg["channel_id"]:
            fetched = member.guild.get_channel(int(cfg["channel_id"]))
            if isinstance(fetched, discord.TextChannel):
                channel = fetched
        if channel is None:
            channel = member.guild.system_channel

        if channel is not None:
            perms = channel.permissions_for(member.guild.me)
            if perms.send_messages:
                try:
                    sent = await channel.send(text)
                    if perms.add_reactions:
                        await self._add_reactions(sent, list(cfg["reactions"] or []))
                except discord.Forbidden:
                    log.warning("Missing access to welcome channel %s", channel.id)
                except discord.HTTPException:
                    log.exception("Failed to send welcome in %s", member.guild.id)

        if cfg["dm_enabled"]:
            try:
                await member.send(render(cfg["dm_message"] or DEFAULT_DM, member, join_count))
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.db.record_leave(member.guild.id, member.id, member.name)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Index people already in servers so stats work before their next join."""
        for guild in self.bot.guilds:
            for member in guild.members:
                try:
                    await self.db.ensure_member_row(
                        guild.id,
                        member.id,
                        member.name,
                        member.global_name,
                        member.joined_at,
                    )
                except Exception:
                    log.exception("Backfill failed for %s in %s", member.id, guild.id)

    # ── slash config ─────────────────────────────────────────

    welcome = app_commands.Group(
        name="welcome",
        description="Welcome messages, reactions, and join tracking",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    @welcome.command(name="setup", description="Set the welcome channel and test a message")
    @app_commands.describe(
        channel="Channel that receives welcome messages",
        message="Template. {mention} {user} {server} {member_count} {join_count}",
        reaction="Emoji to add on the welcome message",
    )
    @is_admin()
    async def welcome_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str | None = None,
        reaction: str | None = "👋",
    ) -> None:
        assert interaction.guild is not None
        gid = interaction.guild.id
        await self.db.set_setting(gid, "welcome.enabled", True)
        await self.db.set_setting(gid, "welcome.channel_id", channel.id)
        if message:
            await self.db.set_setting(gid, "welcome.message", message)
        if reaction:
            await self.db.set_setting(gid, "welcome.reactions", [reaction])
        await interaction.response.send_message(
            f"Welcome messages go to {channel.mention}.",
            ephemeral=True,
        )

    @welcome.command(name="reactions", description="Set one or more reactions added to welcome messages")
    @app_commands.describe(emojis="Emojis separated by spaces, e.g. 👋 🎉")
    @is_admin()
    async def welcome_reactions(self, interaction: discord.Interaction, emojis: str) -> None:
        assert interaction.guild is not None
        parts = [p for p in emojis.split() if p]
        await self.db.set_setting(interaction.guild.id, "welcome.reactions", parts)
        await interaction.response.send_message(
            "Reactions: " + (" ".join(parts) if parts else "(none)"),
            ephemeral=True,
        )

    @welcome.command(name="toggle", description="Enable or disable welcome messages")
    @is_admin()
    async def welcome_toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        assert interaction.guild is not None
        await self.db.set_setting(interaction.guild.id, "welcome.enabled", enabled)
        await interaction.response.send_message(
            "Welcome messages on." if enabled else "Welcome messages off.",
            ephemeral=True,
        )

    @welcome.command(name="dm", description="Optional welcome DM sent to the new member")
    @is_admin()
    async def welcome_dm(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        message: str | None = None,
    ) -> None:
        assert interaction.guild is not None
        await self.db.set_setting(interaction.guild.id, "welcome.dm_enabled", enabled)
        if message:
            await self.db.set_setting(interaction.guild.id, "welcome.dm_message", message)
        await interaction.response.send_message(
            f"Welcome DMs {'on' if enabled else 'off'}.",
            ephemeral=True,
        )

    @welcome.command(name="test", description="Send a sample welcome using your current settings")
    @is_admin()
    async def welcome_test(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None and isinstance(interaction.user, discord.Member)
        cfg = await self._welcome_cfg(interaction.guild.id)
        text = render(cfg["message"] or DEFAULT_MESSAGE, interaction.user, 1)
        await interaction.response.send_message(text)
        msg = await interaction.original_response()
        await self._add_reactions(msg, list(cfg["reactions"] or []))

    @welcome.command(name="status", description="Show welcome + join-tracking status")
    async def welcome_status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        cfg = await self._welcome_cfg(interaction.guild.id)
        ch = interaction.guild.get_channel(int(cfg["channel_id"])) if cfg["channel_id"] else None
        await interaction.response.send_message(
            "\n".join(
                [
                    f"**Enabled:** {cfg['enabled']}",
                    f"**Channel:** {ch.mention if ch else 'system channel / not set'}",
                    f"**Reactions:** {' '.join(cfg['reactions'] or []) or 'none'}",
                    f"**DM:** {cfg['dm_enabled']}",
                    f"**Template:** `{cfg['message']}`",
                ]
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
