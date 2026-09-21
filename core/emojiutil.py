from __future__ import annotations

import re

import discord

CUSTOM_EMOJI = re.compile(r"<a?:([a-zA-Z0-9_]+):(\d+)>")


def parse_emoji(raw: str) -> discord.PartialEmoji | str:
    raw = raw.strip()
    match = CUSTOM_EMOJI.fullmatch(raw)
    if match:
        return discord.PartialEmoji(name=match.group(1), id=int(match.group(2)), animated="a:" in raw[:3])
    return raw


def emoji_key(emoji: discord.PartialEmoji | discord.Emoji | str) -> str:
    if isinstance(emoji, str):
        match = CUSTOM_EMOJI.fullmatch(emoji.strip())
        if match:
            return f"{match.group(1)}:{match.group(2)}"
        return emoji
    if emoji.id:
        return f"{emoji.name}:{emoji.id}"
    return str(emoji)
