from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.access import require
from core.database import Database


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Database = bot.db

    @app_commands.command(name="profile", description="Show when a member joined and their stored stats")
    @app_commands.describe(member="Who to look up (defaults to you)")
    @app_commands.guild_only()
    @require("profile")
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        assert interaction.guild is not None
        target = member or interaction.user
        assert isinstance(target, discord.Member)
        await self.db.upsert_user(target.id, target.name, target.global_name)
        row = await self.db.get_member(interaction.guild.id, target.id)
        if row is None:
            await interaction.response.send_message("No database row yet for that member.", ephemeral=True)
            return
        stats_rows = await self.db.fetchall(
            "SELECT game, stat_key, value FROM stats WHERE guild_id = ? AND user_id = ? ORDER BY game, stat_key",
            (interaction.guild.id, target.id),
        )
        lines = [
            f"**{target.display_name}** (`{target.id}`)",
            f"Joins recorded: **{row['join_count']}**",
            f"Last join: {row['joined_at'] or '—'}",
            f"Last leave: {row['left_at'] or '—'}",
            f"Currently in server: {'yes' if row['is_present'] else 'no'}",
        ]
        if stats_rows:
            lines.append("")
            lines.append("**Stats**")
            for s in stats_rows:
                lines.append(f"- `{s['game']}.{s['stat_key']}` = {s['value']:g}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="leaderboard", description="Top scores for a game stat")
    @app_commands.describe(game="Module name, e.g. rps", stat="Stat key, e.g. wins")
    @app_commands.guild_only()
    @require("profile")
    async def leaderboard(self, interaction: discord.Interaction, game: str, stat: str = "wins") -> None:
        assert interaction.guild is not None
        rows = await self.db.leaderboard(interaction.guild.id, game, stat, 10)
        if not rows:
            await interaction.response.send_message("No stats for that game yet.", ephemeral=True)
            return
        lines = [f"**{game}.{stat}**"]
        for i, row in enumerate(rows, start=1):
            name = row["global_name"] or row["username"] or str(row["user_id"])
            lines.append(f"`{i}.` {name} — {row['value']:g}")
        await interaction.response.send_message("\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Profile(bot))
