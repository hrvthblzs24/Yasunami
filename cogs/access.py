from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.access import COMMANDS, require, role_ids, set_role_ids
from core.checks import ack
from core.database import Database


class Access(commands.Cog):
    """Choose which roles may use which commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Database = bot.db

    access = app_commands.Group(
        name="access",
        description="Control which roles can use Yasunami commands",
        guild_only=True,
        default_permissions=None,
    )

    @access.command(name="show", description="Show which roles can use a command")
    @app_commands.describe(command="Command group")
    @require("access")
    async def show(self, interaction: discord.Interaction, command: str) -> None:
        assert interaction.guild is not None
        if command not in COMMANDS:
            await ack(interaction, "Unknown command key.")
            return
        ids = await role_ids(self.db, interaction.guild.id, command)
        if not ids:
            fallback = COMMANDS[command]["fallback"] or "everyone"
            await ack(interaction, f"**{COMMANDS[command]['label']}** uses the default: `{fallback}`.")
            return
        mentions = " ".join(f"<@&{i}>" for i in ids)
        await ack(interaction, f"**{COMMANDS[command]['label']}** allowed for: {mentions}")

    @access.command(name="allow", description="Allow a role to use a command")
    @app_commands.describe(command="Command group", role="Role that may use it")
    @require("access")
    async def allow(self, interaction: discord.Interaction, command: str, role: discord.Role) -> None:
        assert interaction.guild is not None
        if command not in COMMANDS:
            await ack(interaction, "Unknown command key.")
            return
        ids = await role_ids(self.db, interaction.guild.id, command)
        if role.id not in ids:
            ids.append(role.id)
        await set_role_ids(self.db, interaction.guild.id, command, ids)
        await ack(interaction, f"{role.mention} can use **{COMMANDS[command]['label']}**.")

    @access.command(name="deny", description="Remove a role from a command")
    @app_commands.describe(command="Command group", role="Role to remove")
    @require("access")
    async def deny(self, interaction: discord.Interaction, command: str, role: discord.Role) -> None:
        assert interaction.guild is not None
        if command not in COMMANDS:
            await ack(interaction, "Unknown command key.")
            return
        ids = [i for i in await role_ids(self.db, interaction.guild.id, command) if i != role.id]
        await set_role_ids(self.db, interaction.guild.id, command, ids)
        await ack(interaction, f"{role.mention} removed from **{COMMANDS[command]['label']}**.")

    @access.command(name="clear", description="Reset a command back to the default permission")
    @app_commands.describe(command="Command group")
    @require("access")
    async def clear(self, interaction: discord.Interaction, command: str) -> None:
        assert interaction.guild is not None
        if command not in COMMANDS:
            await ack(interaction, "Unknown command key.")
            return
        await set_role_ids(self.db, interaction.guild.id, command, [])
        await ack(interaction, f"**{COMMANDS[command]['label']}** is back to the default permission.")

    @show.autocomplete("command")
    @allow.autocomplete("command")
    @deny.autocomplete("command")
    @clear.autocomplete("command")
    async def _keys(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        q = current.lower()
        out = []
        for key, meta in COMMANDS.items():
            if q in key or q in meta["label"].lower():
                out.append(app_commands.Choice(name=f"{key} — {meta['label']}", value=key))
        return out[:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Access(bot))
