from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import ack, is_admin
from core.database import Database
from core.defaults import RULES_BODY
from core.emojiutil import emoji_key, parse_emoji

log = logging.getLogger("bot.rules")

DEFAULT_EMOJI = "✅"


class Rules(commands.Cog):
    """Post a rules message. Reacting grants a role (usually Member)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Database = bot.db

    async def _apply_role(
        self,
        guild: discord.Guild,
        user_id: int,
        role_id: int,
        add: bool,
    ) -> None:
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.HTTPException:
                return
        if member.bot:
            return
        role = guild.get_role(role_id)
        if role is None:
            log.warning("Reaction role %s missing in %s", role_id, guild.id)
            return
        me = guild.me
        if me is None or role >= me.top_role:
            log.warning("Bot role is too low to assign %s in %s", role.name, guild.name)
            return
        try:
            if add and role not in member.roles:
                await member.add_roles(role, reason="Accepted server rules")
            elif not add and role in member.roles:
                await member.remove_roles(role, reason="Removed rules reaction")
        except discord.Forbidden:
            log.warning("Missing Manage Roles in %s", guild.name)
        except discord.HTTPException:
            log.exception("Failed to update roles for %s", member.id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return
        if payload.guild_id is None:
            return
        row = await self.db.reaction_role(payload.message_id, emoji_key(payload.emoji))
        if row is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        await self._apply_role(guild, payload.user_id, int(row["role_id"]), add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        row = await self.db.reaction_role(payload.message_id, emoji_key(payload.emoji))
        if row is None or not int(row["remove_on_unreact"]):
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        await self._apply_role(guild, payload.user_id, int(row["role_id"]), add=False)

    rules = app_commands.Group(
        name="rules",
        description="Rules message that grants a role when someone reacts",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    @rules.command(name="post", description="Post a rules message and attach a reaction role")
    @app_commands.describe(
        channel="Where to post the rules",
        role="Role given when they react (create a Member role first)",
        emoji="Reaction emoji",
        title="Embed title",
        body="Rules text. Use {emoji} for the react emoji. Leave empty for the default.",
        remove_on_unreact="Remove the role if they take the reaction off",
    )
    @is_admin()
    async def rules_post(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        emoji: str = DEFAULT_EMOJI,
        title: str = "Server Rules",
        body: str | None = None,
        remove_on_unreact: bool = True,
    ) -> None:
        guild = interaction.guild
        assert guild is not None
        me = guild.me
        if me is None:
            await ack(interaction, "Bot member is not cached yet — try again.")
            return
        if role.is_default() or role.is_integration() or role.managed:
            await ack(interaction, "Pick a normal role you created, not @everyone or a bot role.")
            return
        if role >= me.top_role:
            await ack(
                interaction,
                f"Move my role **above** {role.mention} in Server Settings → Roles.",
            )
            return
        if not me.guild_permissions.manage_roles:
            await ack(interaction, "I need the **Manage Roles** permission.")
            return
        if not channel.permissions_for(me).send_messages:
            await ack(interaction, f"I cannot send messages in {channel.mention}.")
            return

        emoji_obj = parse_emoji(emoji)
        text = (body or RULES_BODY).replace("{emoji}", str(emoji_obj))
        embed = discord.Embed(title=title[:256], description=text[:4096], color=discord.Color.blurple())
        embed.set_footer(text="React to accept the rules and get access.")

        await interaction.response.defer(ephemeral=True)
        try:
            message = await channel.send(embed=embed)
            await message.add_reaction(emoji_obj)
        except discord.HTTPException as exc:
            await interaction.followup.send(f"Could not post or react: {exc}", ephemeral=True)
            return

        await self.db.add_reaction_role(
            guild.id,
            channel.id,
            message.id,
            emoji_key(emoji_obj),
            role.id,
            remove_on_unreact,
        )
        await self.db.set_setting(guild.id, "rules.message_id", message.id)
        await self.db.set_setting(guild.id, "rules.role_id", role.id)

        await interaction.followup.send(
            f"Posted in {channel.mention}. Reacting with {emoji_obj} grants {role.mention}.",
            ephemeral=True,
        )

    @rules.command(name="bind", description="Attach a reaction role to an existing message")
    @app_commands.describe(
        message_id="Message ID (Developer Mode → Copy Message ID)",
        role="Role to grant",
        emoji="Emoji that must already be on the message, or will be added",
    )
    @is_admin()
    async def rules_bind(
        self,
        interaction: discord.Interaction,
        message_id: str,
        role: discord.Role,
        emoji: str = DEFAULT_EMOJI,
        channel: discord.TextChannel | None = None,
        remove_on_unreact: bool = True,
    ) -> None:
        guild = interaction.guild
        assert guild is not None
        if not message_id.isdigit():
            await ack(interaction, "Message ID must be a number.")
            return
        mid = int(message_id)
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await ack(interaction, "Run this in a text channel or pass `channel`.")
            return
        try:
            message = await target.fetch_message(mid)
        except discord.HTTPException:
            await ack(interaction, "Could not find that message in that channel.")
            return
        emoji_obj = parse_emoji(emoji)
        try:
            await message.add_reaction(emoji_obj)
        except discord.HTTPException as exc:
            await ack(interaction, f"Could not add the reaction: {exc}")
            return
        await self.db.add_reaction_role(
            guild.id, target.id, message.id, emoji_key(emoji_obj), role.id, remove_on_unreact
        )
        await ack(interaction, f"Bound {emoji_obj} on that message → {role.mention}.")

    @rules.command(name="clear", description="Stop granting roles from a rules message")
    @is_admin()
    async def rules_clear(self, interaction: discord.Interaction, message_id: str) -> None:
        if not message_id.isdigit():
            await ack(interaction, "Message ID must be a number.")
            return
        await self.db.delete_reaction_roles_for_message(int(message_id))
        await ack(interaction, "Removed reaction-role bindings for that message.")

    @rules.command(name="status", description="List reaction-role bindings in this server")
    async def rules_status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        rows = await self.db.reaction_roles_in_guild(interaction.guild.id)
        if not rows:
            await ack(interaction, "No rules / reaction roles configured.")
            return
        lines = []
        for row in rows:
            role = interaction.guild.get_role(int(row["role_id"]))
            lines.append(
                f"- message `{row['message_id']}` · {row['emoji']} → "
                f"{role.mention if role else row['role_id']}"
            )
        await ack(interaction, "\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Rules(bot))
