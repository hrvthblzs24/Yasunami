from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import ack, is_admin
from core.database import Database
from core.defaults import TEMPVC
from core.utils import bot_has_voice_setup_perms, format_room_name, owner_overwrite


class VoiceCommands(commands.Cog):
    """Slash commands for temp voice setup and room controls."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: Database = bot.db

    def _voice_channel(self, interaction: discord.Interaction) -> discord.VoiceChannel | None:
        if not isinstance(interaction.user, discord.Member):
            return None
        voice = interaction.user.voice
        if voice is None or not isinstance(voice.channel, discord.VoiceChannel):
            return None
        return voice.channel

    async def _owned_room(self, interaction: discord.Interaction):
        channel = self._voice_channel(interaction)
        if channel is None or interaction.guild is None:
            return "Join a temporary voice room first."
        meta = await self.db.room(interaction.guild.id, channel.id)
        if meta is None:
            return "Join a temporary voice room first."
        member = interaction.user
        assert isinstance(member, discord.Member)
        if int(meta["owner_id"]) != member.id and not member.guild_permissions.manage_channels:
            return "Only the room owner (or a moderator) can do that."
        return channel, meta

    setup_group = app_commands.Group(
        name="tempvc",
        description="Configure join-to-create voice channels",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )

    @setup_group.command(name="setup", description="Create a Voice Rooms category + Join to Create lobby")
    @app_commands.describe(category_name="Category name", lobby_name="Lobby voice channel name")
    @is_admin()
    async def tempvc_setup(
        self,
        interaction: discord.Interaction,
        category_name: str | None = None,
        lobby_name: str | None = None,
    ) -> None:
        guild = interaction.guild
        assert guild is not None
        cfg = await self.db.tempvc_config(guild.id)
        category_name = category_name or cfg.get("category_name") or TEMPVC["category_name"]
        lobby_name = lobby_name or cfg.get("lobby_name") or TEMPVC["lobby_name"]

        await interaction.response.defer(ephemeral=True)

        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            try:
                category = await guild.create_category(category_name, reason="TempVC auto-setup")
            except discord.Forbidden:
                await interaction.followup.send("I need **Manage Channels** to create the category.", ephemeral=True)
                return

        missing = bot_has_voice_setup_perms(guild, category)
        if missing:
            await interaction.followup.send(
                "I'm missing these permissions in that category: " + ", ".join(f"`{m}`" for m in missing),
                ephemeral=True,
            )
            return

        try:
            lobby = await category.create_voice_channel(
                lobby_name,
                user_limit=int(cfg.get("lobby_user_limit") or 1),
                reason="TempVC lobby",
            )
        except discord.Forbidden:
            await interaction.followup.send("I need **Manage Channels** to create the lobby.", ephemeral=True)
            return

        await self.db.add_lobby(guild.id, lobby.id, category.id)
        await self.db.set_tempvc(guild.id, enabled=True)
        await interaction.followup.send(
            f"Ready.\nCategory: {category.mention}\nLobby: {lobby.mention}\n"
            "Anyone who joins the lobby gets their own room in that category.",
            ephemeral=True,
        )

    @setup_group.command(name="bind", description="Use an existing voice channel as the join-to-create lobby")
    @is_admin()
    async def tempvc_bind(
        self,
        interaction: discord.Interaction,
        lobby: discord.VoiceChannel,
        category: discord.CategoryChannel | None = None,
    ) -> None:
        guild = interaction.guild
        assert guild is not None
        category = category or lobby.category
        if category is None:
            await ack(interaction, "Pick a category, or put the lobby inside one.")
            return
        missing = bot_has_voice_setup_perms(guild, category)
        if missing:
            await ack(interaction, "I'm missing these permissions: " + ", ".join(f"`{m}`" for m in missing))
            return
        await self.db.add_lobby(guild.id, lobby.id, category.id)
        await self.db.set_tempvc(guild.id, enabled=True)
        await ack(interaction, f"Bound lobby {lobby.mention} → rooms in **{category.name}**.")

    @setup_group.command(name="unbind", description="Stop using a voice channel as a join-to-create lobby")
    @is_admin()
    async def tempvc_unbind(self, interaction: discord.Interaction, lobby: discord.VoiceChannel) -> None:
        assert interaction.guild is not None
        ok = await self.db.remove_lobby(interaction.guild.id, lobby.id)
        await ack(interaction, "Unbound." if ok else "That channel is not a lobby.")

    @setup_group.command(name="config", description="Change how personal rooms are created")
    @is_admin()
    async def tempvc_config(
        self,
        interaction: discord.Interaction,
        enabled: bool | None = None,
        channel_name: str | None = None,
        user_limit: app_commands.Range[int, 0, 99] | None = None,
        bitrate: app_commands.Range[int, 8000, 384000] | None = None,
        one_room_per_owner: bool | None = None,
        delete_delay_seconds: app_commands.Range[int, 0, 60] | None = None,
    ) -> None:
        assert interaction.guild is not None
        updates = {
            "enabled": enabled,
            "channel_name": channel_name,
            "user_limit": user_limit,
            "bitrate": bitrate,
            "one_room_per_owner": one_room_per_owner,
            "delete_delay_seconds": delete_delay_seconds,
        }
        if all(v is None for v in updates.values()):
            cfg = await self.db.tempvc_config(interaction.guild.id)
            lobbies = await self.db.lobbies(interaction.guild.id)
            rooms = await self.db.rooms(interaction.guild.id)
            lines = [
                f"**Enabled:** {cfg['enabled']}",
                f"**Name template:** `{cfg['channel_name']}`",
                f"**User limit:** {cfg['user_limit'] or 'unlimited'}",
                f"**Bitrate:** {cfg['bitrate']}",
                f"**One room per owner:** {cfg['one_room_per_owner']}",
                f"**Delete delay:** {cfg['delete_delay_seconds']}s",
                f"**Lobbies:** {len(lobbies)} · **Live rooms:** {len(rooms)}",
            ]
            for entry in lobbies:
                ch = interaction.guild.get_channel(int(entry["lobby_id"]))
                cat = interaction.guild.get_channel(int(entry["category_id"]))
                lines.append(
                    f"- {ch.mention if ch else entry['lobby_id']} → {cat.name if cat else entry['category_id']}"
                )
            await ack(interaction, "\n".join(lines))
            return

        await self.db.set_tempvc(interaction.guild.id, **updates)
        await ack(interaction, "Updated. Use `/tempvc config` with no options to review.")

    @setup_group.command(name="status", description="Show temp voice status for this server")
    async def tempvc_status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        cfg = await self.db.tempvc_config(interaction.guild.id)
        rooms = await self.db.rooms(interaction.guild.id)
        lobbies = await self.db.lobbies(interaction.guild.id)
        await ack(
            interaction,
            f"{'On' if cfg['enabled'] else 'Off'} · {len(lobbies)} lobby(s) · {len(rooms)} live room(s)",
        )

    vc = app_commands.Group(
        name="vc",
        description="Control the temporary voice room you are in",
        guild_only=True,
    )

    @vc.command(name="rename", description="Rename your temporary voice room")
    async def vc_rename(self, interaction: discord.Interaction, name: str) -> None:
        result = await self._owned_room(interaction)
        if isinstance(result, str):
            await ack(interaction, result)
            return
        channel, _ = result
        try:
            await channel.edit(name=name[:100], reason=f"Renamed by {interaction.user}")
        except discord.HTTPException as exc:
            await ack(interaction, f"Could not rename: {exc}")
            return
        await ack(interaction, f"Renamed to **{channel.name}**.")

    @vc.command(name="limit", description="Set a user limit on your room (0 = unlimited)")
    async def vc_limit(self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]) -> None:
        result = await self._owned_room(interaction)
        if isinstance(result, str):
            await ack(interaction, result)
            return
        channel, _ = result
        try:
            await channel.edit(user_limit=limit, reason=f"Limit set by {interaction.user}")
        except discord.HTTPException as exc:
            await ack(interaction, f"Could not set limit: {exc}")
            return
        await ack(interaction, "Unlimited." if limit == 0 else f"Limit set to **{limit}**.")

    @vc.command(name="lock", description="Lock your room so only current members can join")
    async def vc_lock(self, interaction: discord.Interaction) -> None:
        result = await self._owned_room(interaction)
        if isinstance(result, str):
            await ack(interaction, result)
            return
        channel, _ = result
        assert interaction.guild is not None
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.connect = False
        try:
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason="Room locked")
        except discord.HTTPException as exc:
            await ack(interaction, f"Could not lock: {exc}")
            return
        await ack(interaction, "Room locked.")

    @vc.command(name="unlock", description="Allow everyone to join your room again")
    async def vc_unlock(self, interaction: discord.Interaction) -> None:
        result = await self._owned_room(interaction)
        if isinstance(result, str):
            await ack(interaction, result)
            return
        channel, _ = result
        assert interaction.guild is not None
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.connect = None
        try:
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason="Room unlocked")
        except discord.HTTPException as exc:
            await ack(interaction, f"Could not unlock: {exc}")
            return
        await ack(interaction, "Room unlocked.")

    @vc.command(name="claim", description="Claim an empty-owner room you are sitting in")
    async def vc_claim(self, interaction: discord.Interaction) -> None:
        channel = self._voice_channel(interaction)
        if channel is None or interaction.guild is None:
            await ack(interaction, "You are not in a temporary voice room.")
            return
        meta = await self.db.room(interaction.guild.id, channel.id)
        if meta is None:
            await ack(interaction, "You are not in a temporary voice room.")
            return
        owner_id = int(meta["owner_id"])
        owner = channel.guild.get_member(owner_id)
        if owner is not None and owner in channel.members and owner_id != interaction.user.id:
            await ack(interaction, "The owner is still in the room.")
            return
        assert isinstance(interaction.user, discord.Member)
        cfg = await self.db.tempvc_config(interaction.guild.id)
        try:
            if owner is not None:
                await channel.set_permissions(owner, overwrite=None, reason="Ownership transferred")
            await channel.set_permissions(
                interaction.user,
                overwrite=owner_overwrite(interaction.user, cfg.get("owner_permissions") or []),
                reason="Ownership claimed",
            )
        except discord.HTTPException as exc:
            await ack(interaction, f"Could not claim: {exc}")
            return
        await self.db.set_room_owner(interaction.guild.id, channel.id, interaction.user.id)
        await ack(interaction, f"You now own {channel.mention}.")

    @vc.command(name="transfer", description="Give ownership of your room to someone in it")
    async def vc_transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        result = await self._owned_room(interaction)
        if isinstance(result, str):
            await ack(interaction, result)
            return
        channel, _ = result
        if member not in channel.members:
            await ack(interaction, "That member is not in this room.")
            return
        if member.bot:
            await ack(interaction, "Can't transfer to a bot.")
            return
        assert interaction.guild is not None and isinstance(interaction.user, discord.Member)
        cfg = await self.db.tempvc_config(interaction.guild.id)
        try:
            await channel.set_permissions(interaction.user, overwrite=None, reason="Ownership transferred")
            await channel.set_permissions(
                member,
                overwrite=owner_overwrite(member, cfg.get("owner_permissions") or []),
                reason="Ownership transferred",
            )
        except discord.HTTPException as exc:
            await ack(interaction, f"Could not transfer: {exc}")
            return
        await self.db.set_room_owner(interaction.guild.id, channel.id, member.id)
        await ack(interaction, f"Ownership transferred to {member.mention}.")

    @vc.command(name="kick", description="Disconnect someone from your room")
    async def vc_kick(self, interaction: discord.Interaction, member: discord.Member) -> None:
        result = await self._owned_room(interaction)
        if isinstance(result, str):
            await ack(interaction, result)
            return
        channel, _ = result
        if member not in channel.members:
            await ack(interaction, "That member is not in this room.")
            return
        if member.id == interaction.user.id:
            await ack(interaction, "Leave the channel yourself instead.")
            return
        try:
            await member.move_to(None, reason=f"Kicked from temp VC by {interaction.user}")
        except discord.Forbidden:
            await ack(interaction, "I need **Move Members** to kick.")
            return
        except discord.HTTPException as exc:
            await ack(interaction, f"Could not kick: {exc}")
            return
        await ack(interaction, f"Disconnected {member.mention}.")

    @vc.command(name="resetname", description="Reset your room name to the template")
    async def vc_resetname(self, interaction: discord.Interaction) -> None:
        result = await self._owned_room(interaction)
        if isinstance(result, str):
            await ack(interaction, result)
            return
        channel, meta = result
        assert interaction.guild is not None
        cfg = await self.db.tempvc_config(interaction.guild.id)
        owner = interaction.guild.get_member(int(meta["owner_id"]))
        if owner is None and isinstance(interaction.user, discord.Member):
            owner = interaction.user
        name = format_room_name(cfg["channel_name"], owner)
        try:
            await channel.edit(name=name, reason="Reset room name")
        except discord.HTTPException as exc:
            await ack(interaction, f"Could not rename: {exc}")
            return
        await ack(interaction, f"Reset to **{name}**.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceCommands(bot))
