from __future__ import annotations

import discord
from discord import app_commands


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            raise app_commands.NoPrivateMessage()
        if interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator:
            return True
        raise app_commands.CheckFailure("You need **Manage Server** to use this command.")

    return app_commands.check(predicate)


async def ack(interaction: discord.Interaction, content: str, ephemeral: bool = True) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral)
