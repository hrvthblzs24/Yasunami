from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from core.database import Database

COMMANDS: dict[str, dict[str, Any]] = {
    "access": {"label": "/access", "group": "Admin", "fallback": "administrator"},
    "tempvc": {"label": "/tempvc", "group": "Admin", "fallback": "manage_guild"},
    "welcome": {"label": "/welcome", "group": "Admin", "fallback": "manage_guild"},
    "rules": {"label": "/rules", "group": "Admin", "fallback": "manage_guild"},
    "ban": {"label": "/ban", "group": "Moderation", "fallback": "ban_members"},
    "kick": {"label": "/kick", "group": "Moderation", "fallback": "kick_members"},
    "mute": {"label": "/mute /unmute", "group": "Moderation", "fallback": "moderate_members"},
    "deaf": {"label": "/deaf /undeaf", "group": "Moderation", "fallback": "deafen_members"},
    "msg": {"label": "/msg", "group": "Moderation", "fallback": "manage_messages"},
    "music": {"label": "/play /pause /next /previous /stop /queue", "group": "Music", "fallback": None},
    "profile": {"label": "/profile /leaderboard", "group": "Public", "fallback": None},
    "rps": {"label": "/rps", "group": "Public", "fallback": None},
}


def _ids(raw: Any) -> list[int]:
    if not raw:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out
    try:
        return [int(raw)]
    except (TypeError, ValueError):
        return []


async def role_ids(db: Database, guild_id: int, key: str) -> list[int]:
    return _ids(await db.get_setting(guild_id, f"access.{key}", []))


async def set_role_ids(db: Database, guild_id: int, key: str, ids: list[int]) -> None:
    await db.set_setting(guild_id, f"access.{key}", [int(i) for i in ids])


async def allowed(db: Database, member: discord.Member, key: str) -> bool:
    if member.guild_permissions.administrator:
        return True
    assigned = await role_ids(db, member.guild.id, key)
    if assigned:
        have = {role.id for role in member.roles}
        return any(role_id in have for role_id in assigned)
    fallback = COMMANDS.get(key, {}).get("fallback")
    if not fallback:
        return True
    return bool(getattr(member.guild_permissions, fallback, False))


def require(key: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            raise app_commands.NoPrivateMessage()
        db: Database = interaction.client.db  # type: ignore[attr-defined]
        if await allowed(db, interaction.user, key):
            return True
        raise app_commands.CheckFailure(
            f"Your roles cannot use **{COMMANDS.get(key, {}).get('label', key)}**."
        )

    return app_commands.check(predicate)
