from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from core.defaults import TEMPVC
from core.paths import DATA_DIR, DB_PATH

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    global_name TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    joined_at   TEXT,
    left_at     TEXT,
    join_count  INTEGER NOT NULL DEFAULT 0,
    is_present  INTEGER NOT NULL DEFAULT 1,
    extra       TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS member_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    action      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_member
    ON member_events (guild_id, user_id, created_at);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER NOT NULL,
    key      TEXT NOT NULL,
    value    TEXT NOT NULL,
    PRIMARY KEY (guild_id, key)
);

CREATE TABLE IF NOT EXISTS stats (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    game        TEXT NOT NULL,
    stat_key    TEXT NOT NULL,
    value       REAL NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, game, stat_key)
);

CREATE INDEX IF NOT EXISTS idx_stats_leaderboard
    ON stats (guild_id, game, stat_key, value DESC);

CREATE TABLE IF NOT EXISTS tempvc_lobbies (
    guild_id    INTEGER NOT NULL,
    lobby_id    INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, lobby_id)
);

CREATE TABLE IF NOT EXISTS tempvc_rooms (
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    owner_id    INTEGER NOT NULL,
    lobby_id    INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_rooms_owner
    ON tempvc_rooms (guild_id, owner_id);

CREATE TABLE IF NOT EXISTS reaction_roles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id            INTEGER NOT NULL,
    channel_id          INTEGER NOT NULL,
    message_id          INTEGER NOT NULL,
    emoji               TEXT NOT NULL,
    role_id             INTEGER NOT NULL,
    remove_on_unreact   INTEGER NOT NULL DEFAULT 1,
    UNIQUE (message_id, emoji)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Single SQLite connection used by every cog."""

    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    @property
    def raw(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database.connect() was not called")
        return self._db

    async def connect(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '2')"
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        cur = await self.raw.execute(sql, params)
        await self.raw.commit()
        return cur

    async def fetchone(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
        cur = await self.raw.execute(sql, params)
        return await cur.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        cur = await self.raw.execute(sql, params)
        return await cur.fetchall()

    async def wipe_guild(self, guild_id: int) -> None:
        for table in (
            "members",
            "member_events",
            "guild_settings",
            "stats",
            "tempvc_lobbies",
            "tempvc_rooms",
            "reaction_roles",
        ):
            await self.execute(f"DELETE FROM {table} WHERE guild_id = ?", (guild_id,))

    # ── users / members ──────────────────────────────────────

    async def upsert_user(self, user_id: int, username: str | None, global_name: str | None) -> None:
        now = _now()
        await self.execute(
            """
            INSERT INTO users (user_id, username, global_name, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                global_name = excluded.global_name,
                last_seen = excluded.last_seen
            """,
            (user_id, username, global_name, now, now),
        )

    async def record_join(
        self,
        guild_id: int,
        user_id: int,
        username: str | None,
        global_name: str | None,
        joined_at: datetime | None = None,
    ) -> int:
        await self.upsert_user(user_id, username, global_name)
        stamp = (joined_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        row = await self.fetchone(
            "SELECT join_count FROM members WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if row is None:
            await self.execute(
                """
                INSERT INTO members (guild_id, user_id, joined_at, left_at, join_count, is_present)
                VALUES (?, ?, ?, NULL, 1, 1)
                """,
                (guild_id, user_id, stamp),
            )
            join_count = 1
        else:
            await self.execute(
                """
                UPDATE members
                SET joined_at = ?, left_at = NULL, join_count = join_count + 1, is_present = 1
                WHERE guild_id = ? AND user_id = ?
                """,
                (stamp, guild_id, user_id),
            )
            join_count = int(row["join_count"]) + 1
        await self.execute(
            "INSERT INTO member_events (guild_id, user_id, action, created_at) VALUES (?, ?, 'join', ?)",
            (guild_id, user_id, stamp),
        )
        return join_count

    async def record_leave(self, guild_id: int, user_id: int, username: str | None = None) -> None:
        if username:
            await self.upsert_user(user_id, username, None)
        stamp = _now()
        await self.execute(
            """
            UPDATE members
            SET left_at = ?, is_present = 0
            WHERE guild_id = ? AND user_id = ?
            """,
            (stamp, guild_id, user_id),
        )
        await self.execute(
            "INSERT INTO member_events (guild_id, user_id, action, created_at) VALUES (?, ?, 'leave', ?)",
            (guild_id, user_id, stamp),
        )

    async def get_member(self, guild_id: int, user_id: int) -> aiosqlite.Row | None:
        return await self.fetchone(
            """
            SELECT m.*, u.username, u.global_name, u.first_seen, u.last_seen
            FROM members m
            LEFT JOIN users u ON u.user_id = m.user_id
            WHERE m.guild_id = ? AND m.user_id = ?
            """,
            (guild_id, user_id),
        )

    async def ensure_member_row(
        self,
        guild_id: int,
        user_id: int,
        username: str | None,
        global_name: str | None,
        joined_at: datetime | None,
    ) -> None:
        await self.upsert_user(user_id, username, global_name)
        stamp = (joined_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        await self.execute(
            """
            INSERT OR IGNORE INTO members
                (guild_id, user_id, joined_at, join_count, is_present)
            VALUES (?, ?, ?, 1, 1)
            """,
            (guild_id, user_id, stamp),
        )

    # ── guild settings ───────────────────────────────────────

    async def get_setting(self, guild_id: int, key: str, default: Any = None) -> Any:
        row = await self.fetchone(
            "SELECT value FROM guild_settings WHERE guild_id = ? AND key = ?",
            (guild_id, key),
        )
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    async def set_setting(self, guild_id: int, key: str, value: Any) -> None:
        await self.execute(
            """
            INSERT INTO guild_settings (guild_id, key, value) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
            """,
            (guild_id, key, json.dumps(value)),
        )

    # ── stats ────────────────────────────────────────────────

    async def add_stat(
        self,
        guild_id: int,
        user_id: int,
        game: str,
        stat_key: str,
        amount: float = 1,
    ) -> float:
        now = _now()
        await self.execute(
            """
            INSERT INTO stats (guild_id, user_id, game, stat_key, value, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, game, stat_key) DO UPDATE SET
                value = value + excluded.value,
                updated_at = excluded.updated_at
            """,
            (guild_id, user_id, game, stat_key, amount, now),
        )
        row = await self.fetchone(
            """
            SELECT value FROM stats
            WHERE guild_id = ? AND user_id = ? AND game = ? AND stat_key = ?
            """,
            (guild_id, user_id, game, stat_key),
        )
        return float(row["value"]) if row else amount

    async def set_stat(
        self,
        guild_id: int,
        user_id: int,
        game: str,
        stat_key: str,
        value: float,
    ) -> None:
        await self.execute(
            """
            INSERT INTO stats (guild_id, user_id, game, stat_key, value, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, game, stat_key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (guild_id, user_id, game, stat_key, value, _now()),
        )

    async def get_stat(
        self,
        guild_id: int,
        user_id: int,
        game: str,
        stat_key: str,
        default: float = 0,
    ) -> float:
        row = await self.fetchone(
            """
            SELECT value FROM stats
            WHERE guild_id = ? AND user_id = ? AND game = ? AND stat_key = ?
            """,
            (guild_id, user_id, game, stat_key),
        )
        return float(row["value"]) if row else default

    async def leaderboard(
        self,
        guild_id: int,
        game: str,
        stat_key: str,
        limit: int = 10,
    ) -> list[aiosqlite.Row]:
        return await self.fetchall(
            """
            SELECT s.user_id, s.value, u.username, u.global_name
            FROM stats s
            LEFT JOIN users u ON u.user_id = s.user_id
            WHERE s.guild_id = ? AND s.game = ? AND s.stat_key = ?
            ORDER BY s.value DESC
            LIMIT ?
            """,
            (guild_id, game, stat_key, limit),
        )

    # ── temp voice ───────────────────────────────────────────

    async def tempvc_config(self, guild_id: int) -> dict[str, Any]:
        cfg = dict(TEMPVC)
        for key in cfg:
            stored = await self.get_setting(guild_id, f"tempvc.{key}", None)
            if stored is not None:
                cfg[key] = stored
        return cfg

    async def set_tempvc(self, guild_id: int, **kwargs: Any) -> dict[str, Any]:
        for key, value in kwargs.items():
            if value is None:
                continue
            await self.set_setting(guild_id, f"tempvc.{key}", value)
        return await self.tempvc_config(guild_id)

    async def add_lobby(self, guild_id: int, lobby_id: int, category_id: int) -> None:
        await self.execute(
            """
            INSERT INTO tempvc_lobbies (guild_id, lobby_id, category_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, lobby_id) DO UPDATE SET category_id = excluded.category_id
            """,
            (guild_id, lobby_id, category_id),
        )

    async def remove_lobby(self, guild_id: int, lobby_id: int) -> bool:
        cur = await self.execute(
            "DELETE FROM tempvc_lobbies WHERE guild_id = ? AND lobby_id = ?",
            (guild_id, lobby_id),
        )
        return cur.rowcount > 0

    async def lobbies(self, guild_id: int) -> list[aiosqlite.Row]:
        return await self.fetchall(
            "SELECT lobby_id, category_id FROM tempvc_lobbies WHERE guild_id = ?",
            (guild_id,),
        )

    async def lobby_ids(self, guild_id: int) -> set[int]:
        return {int(r["lobby_id"]) for r in await self.lobbies(guild_id)}

    async def lobby_entry(self, guild_id: int, lobby_id: int) -> aiosqlite.Row | None:
        return await self.fetchone(
            "SELECT lobby_id, category_id FROM tempvc_lobbies WHERE guild_id = ? AND lobby_id = ?",
            (guild_id, lobby_id),
        )

    async def register_room(
        self,
        guild_id: int,
        channel_id: int,
        owner_id: int,
        lobby_id: int,
        category_id: int,
    ) -> None:
        await self.execute(
            """
            INSERT INTO tempvc_rooms (guild_id, channel_id, owner_id, lobby_id, category_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                owner_id = excluded.owner_id,
                lobby_id = excluded.lobby_id,
                category_id = excluded.category_id
            """,
            (guild_id, channel_id, owner_id, lobby_id, category_id),
        )

    async def unregister_room(self, guild_id: int, channel_id: int) -> None:
        await self.execute(
            "DELETE FROM tempvc_rooms WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )

    async def room(self, guild_id: int, channel_id: int) -> aiosqlite.Row | None:
        return await self.fetchone(
            "SELECT * FROM tempvc_rooms WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )

    async def rooms(self, guild_id: int) -> list[aiosqlite.Row]:
        return await self.fetchall(
            "SELECT * FROM tempvc_rooms WHERE guild_id = ?",
            (guild_id,),
        )

    async def room_ids(self, guild_id: int) -> set[int]:
        return {int(r["channel_id"]) for r in await self.rooms(guild_id)}

    async def owner_room(self, guild_id: int, owner_id: int) -> aiosqlite.Row | None:
        return await self.fetchone(
            "SELECT * FROM tempvc_rooms WHERE guild_id = ? AND owner_id = ?",
            (guild_id, owner_id),
        )

    async def set_room_owner(self, guild_id: int, channel_id: int, owner_id: int) -> None:
        await self.execute(
            "UPDATE tempvc_rooms SET owner_id = ? WHERE guild_id = ? AND channel_id = ?",
            (owner_id, guild_id, channel_id),
        )

    # ── reaction roles / rules ───────────────────────────────

    async def add_reaction_role(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        emoji: str,
        role_id: int,
        remove_on_unreact: bool = True,
    ) -> None:
        await self.execute(
            """
            INSERT INTO reaction_roles
                (guild_id, channel_id, message_id, emoji, role_id, remove_on_unreact)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id, emoji) DO UPDATE SET
                role_id = excluded.role_id,
                channel_id = excluded.channel_id,
                guild_id = excluded.guild_id,
                remove_on_unreact = excluded.remove_on_unreact
            """,
            (guild_id, channel_id, message_id, emoji, role_id, int(remove_on_unreact)),
        )

    async def reaction_role(self, message_id: int, emoji: str) -> aiosqlite.Row | None:
        return await self.fetchone(
            "SELECT * FROM reaction_roles WHERE message_id = ? AND emoji = ?",
            (message_id, emoji),
        )

    async def reaction_roles_in_guild(self, guild_id: int) -> list[aiosqlite.Row]:
        return await self.fetchall(
            "SELECT * FROM reaction_roles WHERE guild_id = ? ORDER BY id",
            (guild_id,),
        )

    async def delete_reaction_roles_for_message(self, message_id: int) -> None:
        await self.execute("DELETE FROM reaction_roles WHERE message_id = ?", (message_id,))
