from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs

from aiohttp import web
from dotenv import load_dotenv

from core.access import COMMANDS, role_ids, set_role_ids
from core.defaults import MOD, MUSIC, TEMPVC, WELCOME_DM, WELCOME_MESSAGE
from core.paths import ROOT

if TYPE_CHECKING:
    from discord.ext import commands
    from core.database import Database

log = logging.getLogger("bot.web")
WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = WEB_DIR / "templates"
STATIC = WEB_DIR / "static"
COOKIE = "dash_auth"
THEME_COOKIE = "dash_theme"
THEMES = ("sand", "ink", "ocean", "sakura", "matcha", "violet")


def _secret() -> str:
    return os.getenv("DASHBOARD_SECRET", "change-me")


def dashboard_bind() -> tuple[str, int]:
    load_dotenv(ROOT / ".env", override=True)
    host = (os.getenv("DASHBOARD_HOST") or "127.0.0.1").strip().strip("\"'")
    raw = (os.getenv("DASHBOARD_PORT") or "8080").strip().strip("\"'")
    try:
        port = int(raw)
    except ValueError:
        port = 8080
    if port < 1 or port > 65535:
        port = 8080
    return host, port


def _token() -> str:
    return hashlib.sha256(f"dash:{_secret()}".encode()).hexdigest()


def _authed(request: web.Request) -> bool:
    return request.cookies.get(COOKIE) == _token()


def _read(template: str) -> str:
    return (TEMPLATES / template).read_text(encoding="utf-8")


def _render(template: str, *, raw: dict[str, str] | None = None, **values: Any) -> str:
    text = _read(template)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", html.escape("" if value is None else str(value)))
    for key, value in (raw or {}).items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _theme(request: web.Request) -> str:
    name = (request.cookies.get(THEME_COOKIE) or "ink").strip()
    return name if name in THEMES else "ink"


def _page(request: web.Request, title: str, body: str, flash: str = "") -> web.Response:
    return web.Response(
        text=_render("base.html", title=title, theme=_theme(request), raw={"flash": flash, "body": body}),
        content_type="text/html",
    )


def flash_ok(text: str) -> str:
    return f'<div class="flash">{html.escape(text)}</div>'


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


class Dashboard:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.runner: web.AppRunner | None = None

    @property
    def db(self) -> Database:
        return self.bot.db

    def app(self) -> web.Application:
        app = web.Application()
        app["dash"] = self
        app.router.add_get("/login", self.login_get)
        app.router.add_post("/login", self.login_post)
        app.router.add_get("/logout", self.logout)
        app.router.add_get("/", self.home)
        app.router.add_get("/system", self.system)
        app.router.add_post("/system/reload", self.reload_cogs)
        app.router.add_get("/guild/{guild_id}", self.guild)
        app.router.add_post("/guild/{guild_id}/tempvc", self.save_tempvc)
        app.router.add_post("/guild/{guild_id}/welcome", self.save_welcome)
        app.router.add_post("/guild/{guild_id}/music", self.save_music)
        app.router.add_post("/guild/{guild_id}/mod", self.save_mod)
        app.router.add_post("/guild/{guild_id}/access", self.save_access)
        app.router.add_post("/guild/{guild_id}/setting", self.save_setting)
        app.router.add_get("/theme/{name}", self.set_theme)
        app.router.add_static("/static", STATIC)
        return app

    async def start(self) -> None:
        host, port = dashboard_bind()
        self.host, self.port = host, port
        self.runner = web.AppRunner(self.app())
        await self.runner.setup()
        site = web.TCPSite(self.runner, host, port)
        try:
            await site.start()
        except OSError as exc:
            await self.runner.cleanup()
            self.runner = None
            log.error("Dashboard could not bind http://%s:%s (%s)", host, port, exc)
            raise
        log.info("Yasunami dashboard: http://%s:%s", host, port)

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    def _need_auth(self, request: web.Request) -> web.StreamResponse | None:
        if not _authed(request):
            raise web.HTTPFound("/login")
        return None

    async def login_get(self, request: web.Request) -> web.Response:
        if _authed(request):
            raise web.HTTPFound("/")
        return web.Response(text=_render("login.html", theme=_theme(request), raw={"error": ""}), content_type="text/html")

    async def login_post(self, request: web.Request) -> web.StreamResponse:
        data = parse_qs(await request.text())
        secret = (data.get("secret") or [""])[0]
        if not hmac.compare_digest(secret, _secret()):
            page = _render("login.html", theme=_theme(request), raw={"error": '<p class="err">Wrong secret.</p>'})
            return web.Response(text=page, content_type="text/html", status=401)
        resp = web.HTTPFound("/")
        resp.set_cookie(COOKIE, _token(), httponly=True, samesite="Lax")
        raise resp

    async def logout(self, request: web.Request) -> web.StreamResponse:
        resp = web.HTTPFound("/login")
        resp.del_cookie(COOKIE)
        raise resp

    async def home(self, request: web.Request) -> web.Response:
        self._need_auth(request)
        cards = [_render("partials/guild_card.html", id=g.id, name=g.name, members=g.member_count) for g in self.bot.guilds]
        if not cards:
            cards.append('<div class="card">Bot is not in any servers yet.</div>')
        return _page(request, "Servers", _render("home.html", raw={"cards": "".join(cards)}))

    async def system(self, request: web.Request) -> web.Response:
        self._need_auth(request)
        user = self.bot.user
        body = _render(
            "system.html",
            user=user,
            user_id=user.id if user else "",
            dashboard_url=f"http://{getattr(self, 'host', '127.0.0.1')}:{getattr(self, 'port', 8080)}",
            database=self.db.path,
            root=ROOT,
            raw={"extensions": "".join(f"<li><code>{_e(name)}</code></li>" for name in self.bot.extensions)},
        )
        return _page(request, "System", body)

    async def reload_cogs(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        for ext in list(self.bot.extensions):
            try:
                await self.bot.reload_extension(ext)
            except Exception as exc:
                log.error("Reload %s: %s", ext, exc)
        raise web.HTTPFound("/system")

    async def guild(self, request: web.Request) -> web.Response:
        self._need_auth(request)
        guild_id = int(request.match_info["guild_id"])
        guild = self.bot.get_guild(guild_id)
        name = guild.name if guild else str(guild_id)
        cfg = await self.db.tempvc_config(guild_id)
        welcome_enabled = await self.db.get_setting(guild_id, "welcome.enabled", True)
        welcome_channel = await self.db.get_setting(guild_id, "welcome.channel_id", "")
        welcome_message = await self.db.get_setting(guild_id, "welcome.message", WELCOME_MESSAGE)
        welcome_dm = await self.db.get_setting(guild_id, "welcome.dm_enabled", False)
        welcome_dm_msg = await self.db.get_setting(guild_id, "welcome.dm_message", WELCOME_DM)
        reactions = await self.db.get_setting(guild_id, "welcome.reactions", ["👋"])
        reactions_s = " ".join(str(x) for x in reactions) if isinstance(reactions, list) else str(reactions or "")
        lobbies = await self.db.lobbies(guild_id)
        rooms = await self.db.rooms(guild_id)
        rules = await self.db.reaction_roles_in_guild(guild_id)
        events = await self.db.fetchall("SELECT user_id, action, created_at FROM member_events WHERE guild_id = ? ORDER BY id DESC LIMIT 15", (guild_id,))
        lobby_rows = "".join(f"<tr><td>{row['lobby_id']}</td><td>{row['category_id']}</td></tr>" for row in lobbies) or "<tr><td colspan='2'>None</td></tr>"
        room_rows = "".join(f"<tr><td>{row['channel_id']}</td><td>{row['owner_id']}</td></tr>" for row in rooms) or "<tr><td colspan='2'>No live rooms</td></tr>"
        rule_rows = "".join(f"<tr><td>{row['message_id']}</td><td>{_e(row['emoji'])}</td><td>{row['role_id']}</td></tr>" for row in rules) or "<tr><td colspan='3'>None</td></tr>"
        event_rows = "".join(f"<tr><td>{row['user_id']}</td><td>{_e(row['action'])}</td><td>{_e(row['created_at'])}</td></tr>" for row in events) or "<tr><td colspan='3'>No joins yet</td></tr>"
        body = _render(
            "guild.html",
            name=name, guild_id=guild_id,
            channel_name=cfg.get("channel_name") or TEMPVC["channel_name"],
            user_limit=cfg.get("user_limit", 0), bitrate=cfg.get("bitrate", 64000),
            delete_delay_seconds=cfg.get("delete_delay_seconds", 2),
            welcome_channel=welcome_channel, welcome_message=welcome_message,
            reactions=reactions_s, welcome_dm=welcome_dm_msg,
            music_volume=await self.db.get_setting(guild_id, "music.volume", MUSIC["volume"]),
            music_queue=await self.db.get_setting(guild_id, "music.max_queue", MUSIC["max_queue"]),
            mute_minutes=await self.db.get_setting(guild_id, "mod.mute.minutes", MOD["mute.minutes"]),
            raw={
                "enabled_checked": "checked" if cfg.get("enabled") else "",
                "one_room_checked": "checked" if cfg.get("one_room_per_owner") else "",
                "welcome_checked": "checked" if welcome_enabled else "",
                "dm_checked": "checked" if welcome_dm else "",
                "music_checked": "checked" if await self.db.get_setting(guild_id, "music.enabled", MUSIC["enabled"]) else "",
                "announce_checked": "checked" if await self.db.get_setting(guild_id, "music.announce", MUSIC["announce"]) else "",
                "ban_checked": "checked" if await self.db.get_setting(guild_id, "mod.ban.enabled", MOD["ban.enabled"]) else "",
                "kick_checked": "checked" if await self.db.get_setting(guild_id, "mod.kick.enabled", MOD["kick.enabled"]) else "",
                "mute_checked": "checked" if await self.db.get_setting(guild_id, "mod.mute.enabled", MOD["mute.enabled"]) else "",
                "deaf_checked": "checked" if await self.db.get_setting(guild_id, "mod.deaf.enabled", MOD["deaf.enabled"]) else "",
                "msg_checked": "checked" if await self.db.get_setting(guild_id, "mod.msg.enabled", MOD["msg.enabled"]) else "",
                "lobby_rows": lobby_rows, "room_rows": room_rows, "rule_rows": rule_rows, "event_rows": event_rows,
                "access_blocks": await self._access_blocks(guild, guild_id),
            },
        )
        q = request.rel_url.query.get("ok")
        return _page(request, name, body, flash_ok(q) if q else "")

    async def save_tempvc(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        guild_id = int(request.match_info["guild_id"])
        form = parse_qs(await request.text())
        await self.db.set_tempvc(
            guild_id, enabled="enabled" in form,
            channel_name=(form.get("channel_name") or [""])[0] or TEMPVC["channel_name"],
            user_limit=int((form.get("user_limit") or ["0"])[0] or 0),
            bitrate=int((form.get("bitrate") or ["64000"])[0] or 64000),
            delete_delay_seconds=int((form.get("delete_delay_seconds") or ["2"])[0] or 2),
            one_room_per_owner="one_room_per_owner" in form,
        )
        raise web.HTTPFound(f"/guild/{guild_id}?ok=Temp+voice+saved")

    async def save_welcome(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        guild_id = int(request.match_info["guild_id"])
        form = parse_qs(await request.text())
        channel_raw = (form.get("channel_id") or [""])[0].strip()
        await self.db.set_setting(guild_id, "welcome.enabled", "enabled" in form)
        await self.db.set_setting(guild_id, "welcome.channel_id", int(channel_raw) if channel_raw.isdigit() else None)
        await self.db.set_setting(guild_id, "welcome.message", (form.get("message") or [WELCOME_MESSAGE])[0])
        await self.db.set_setting(guild_id, "welcome.reactions", [p for p in (form.get("reactions") or [""])[0].split() if p] or ["👋"])
        await self.db.set_setting(guild_id, "welcome.dm_enabled", "dm_enabled" in form)
        await self.db.set_setting(guild_id, "welcome.dm_message", (form.get("dm_message") or [WELCOME_DM])[0])
        raise web.HTTPFound(f"/guild/{guild_id}?ok=Welcome+saved")

    async def save_music(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        guild_id = int(request.match_info["guild_id"])
        form = parse_qs(await request.text())
        await self.db.set_setting(guild_id, "music.enabled", "enabled" in form)
        await self.db.set_setting(guild_id, "music.announce", "announce" in form)
        await self.db.set_setting(guild_id, "music.volume", int((form.get("volume") or ["80"])[0] or 80))
        await self.db.set_setting(guild_id, "music.max_queue", int((form.get("max_queue") or ["50"])[0] or 50))
        raise web.HTTPFound(f"/guild/{guild_id}?ok=Music+saved")

    async def save_mod(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        guild_id = int(request.match_info["guild_id"])
        form = parse_qs(await request.text())
        await self.db.set_setting(guild_id, "mod.ban.enabled", "ban_enabled" in form)
        await self.db.set_setting(guild_id, "mod.kick.enabled", "kick_enabled" in form)
        await self.db.set_setting(guild_id, "mod.mute.enabled", "mute_enabled" in form)
        await self.db.set_setting(guild_id, "mod.deaf.enabled", "deaf_enabled" in form)
        await self.db.set_setting(guild_id, "mod.msg.enabled", "msg_enabled" in form)
        await self.db.set_setting(guild_id, "mod.mute.minutes", int((form.get("mute_minutes") or ["10"])[0] or 10))
        raise web.HTTPFound(f"/guild/{guild_id}?ok=Moderation+saved")

    async def set_theme(self, request: web.Request) -> web.StreamResponse:
        name = request.match_info.get("name", "ink")
        if name not in THEMES:
            name = "ink"
        resp = web.HTTPFound(request.headers.get("Referer") or "/")
        resp.set_cookie(THEME_COOKIE, name, max_age=60 * 60 * 24 * 365, path="/", samesite="Lax")
        raise resp

    async def _access_blocks(self, guild, guild_id: int) -> str:
        roles = [r for r in guild.roles if not r.is_default()] if guild is not None else []
        roles.sort(key=lambda r: r.position, reverse=True)
        if not roles:
            return "<p class='muted'>Join the bot to this server to list roles.</p>"
        blocks = []
        for key, meta in COMMANDS.items():
            selected = set(await role_ids(self.db, guild_id, key))
            chips = [f'<label><input type="checkbox" name="access_{key}" value="{role.id}" {"checked" if role.id in selected else ""}> {_e(role.name)}</label>' for role in roles]
            fallback = meta["fallback"] or "everyone"
            blocks.append(f"<h2>{_e(meta['label'])}</h2><p class='muted'>{_e(meta['group'])} · default <code>{_e(fallback)}</code></p><div class='roles'>{''.join(chips)}</div>")
        return "".join(blocks)

    async def save_access(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        guild_id = int(request.match_info["guild_id"])
        form = parse_qs(await request.text())
        for key in COMMANDS:
            ids = [int(item) for item in (form.get(f"access_{key}") or []) if str(item).isdigit()]
            await set_role_ids(self.db, guild_id, key, ids)
        raise web.HTTPFound(f"/guild/{guild_id}?ok=Access+saved")

    async def save_setting(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        guild_id = int(request.match_info["guild_id"])
        form = parse_qs(await request.text())
        key = (form.get("key") or [""])[0].strip()
        raw = (form.get("value") or [""])[0]
        if not key:
            raise web.HTTPFound(f"/guild/{guild_id}?ok=Missing+key")
        value: Any = raw
        lowered = raw.strip().lower()
        if lowered in {"true", "false"}:
            value = lowered == "true"
        elif raw.strip() and raw.strip().lstrip("-").isdigit():
            value = int(raw.strip())
        await self.db.set_setting(guild_id, key, value)
        raise web.HTTPFound(f"/guild/{guild_id}?ok=Saved+{key}")


async def start_dashboard(bot: commands.Bot) -> Dashboard:
    dash = Dashboard(bot)
    await dash.start()
    bot.dashboard = dash  # type: ignore[attr-defined]

    async def restart_dashboard() -> None:
        await dash.restart()

    bot.restart_dashboard = restart_dashboard  # type: ignore[attr-defined]
    return dash
