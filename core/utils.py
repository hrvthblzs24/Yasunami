from __future__ import annotations

import re
from typing import Iterable

import discord

NAME_MAX = 100

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def sanitize_channel_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip()
    cleaned = cleaned.replace("\n", " ")
    if not cleaned:
        cleaned = "Voice Room"
    return cleaned[:NAME_MAX]


def format_room_name(template: str, member: discord.Member) -> str:
    mapping = {
        "name": member.name,
        "username": member.name,
        "display_name": member.display_name,
        "nick": member.nick or member.display_name,
        "global_name": member.global_name or member.name,
        "id": str(member.id),
        "discriminator": member.discriminator,
        "guild": member.guild.name,
    }

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(mapping.get(key, match.group(0)))

    return sanitize_channel_name(PLACEHOLDER_RE.sub(repl, template))


PERM_MAP = {
    "manage_channels": "manage_channels",
    "manage_permissions": "manage_roles",
    "manage_roles": "manage_roles",
    "mute_members": "mute_members",
    "deafen_members": "deafen_members",
    "move_members": "move_members",
    "connect": "connect",
    "speak": "speak",
    "stream": "stream",
    "use_voice_activation": "use_voice_activation",
    "priority_speaker": "priority_speaker",
    "view_channel": "view_channel",
}


def owner_overwrite(member: discord.Member, perm_names: Iterable[str]) -> discord.PermissionOverwrite:
    kwargs: dict[str, bool] = {}
    for raw in perm_names:
        key = PERM_MAP.get(raw.lower())
        if key:
            kwargs[key] = True
    if not kwargs:
        kwargs["manage_channels"] = True
        kwargs["connect"] = True
        kwargs["speak"] = True
    return discord.PermissionOverwrite(**kwargs)


def bot_has_voice_setup_perms(guild: discord.Guild, category: discord.CategoryChannel | None) -> list[str]:
    me = guild.me
    missing: list[str] = []
    target = category or guild
    perms = target.permissions_for(me) if hasattr(target, "permissions_for") else me.guild_permissions
    needed = {
        "view_channel": perms.view_channel,
        "manage_channels": perms.manage_channels,
        "move_members": perms.move_members,
        "connect": perms.connect,
    }
    for name, ok in needed.items():
        if not ok:
            missing.append(name)
    return missing
