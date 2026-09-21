from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from core.database import Database

CHOICES = ("rock", "paper", "scissors")
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


class RockPaperScissors(commands.Cog):
    """Example minigame that writes into the shared stats table."""

    GAME = "rps"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Database = bot.db

    @app_commands.command(name="rps", description="Rock paper scissors — scores are stored in the database")
    @app_commands.describe(choice="Your throw")
    @app_commands.choices(
        choice=[
            app_commands.Choice(name="Rock", value="rock"),
            app_commands.Choice(name="Paper", value="paper"),
            app_commands.Choice(name="Scissors", value="scissors"),
        ]
    )
    @app_commands.guild_only()
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]) -> None:
        assert interaction.guild is not None
        you = choice.value
        bot_pick = random.choice(CHOICES)
        await self.db.upsert_user(interaction.user.id, interaction.user.name, interaction.user.global_name)
        await self.db.add_stat(interaction.guild.id, interaction.user.id, self.GAME, "plays", 1)

        if you == bot_pick:
            result = f"Tie — we both picked **{you}**."
            key = "ties"
        elif BEATS[you] == bot_pick:
            result = f"You win — **{you}** beats **{bot_pick}**."
            key = "wins"
        else:
            result = f"You lose — **{bot_pick}** beats **{you}**."
            key = "losses"

        value = await self.db.add_stat(interaction.guild.id, interaction.user.id, self.GAME, key, 1)
        wins = await self.db.get_stat(interaction.guild.id, interaction.user.id, self.GAME, "wins")
        await interaction.response.send_message(f"{result}\n{key}: **{value:g}** · wins total: **{wins:g}**")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RockPaperScissors(bot))
