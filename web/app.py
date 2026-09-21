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

from core.defaults import TEMPVC, WELCOME_DM, WELCOME_MESSAGE
from core.paths import ROOT

if TYPE_CHECKING:
    from discord.ext import commands

    from core.database import Database

log = logging.getLogger("bot.web")
TEMPLATES = Path(__file__).resolve().parent / "templates"
COOKIE = "dash_auth"


def _secret() -> str:
    return os.getenv("DASHBOARD_SECRET", "change-me")


def _token() -> str:
    return hashlib.sha256(f"dash:{_secret()}".encode()).hexdigest()


def _authed(request: web.Request) -> bool:
    return request.cookies.get(COOKIE) == _token()


def _read(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _page(title: str, body: str, flash: str = "") -> web.Response:
    raw = _read("base.html")
    html_out = (
        raw.replace("{{title}}", html.escape(title))
        .replace("{{flash}}", flash)
        .replace("{{body}}", body)
    )
    return web.Response(text=html_out, content_type="text/html")


def flash_ok(text: str) -> str:
    return f'<div class="flash">{html.escape(text)}</div>'


def flash_err(text: str) -> str:
    return f'<div class="flash err">{html.escape(text)}</div>'


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
        app.router.add_post("/guild/{guild_id}/setting", self.save_setting)
        return app

    async def start(self) -> None:
        host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
        port = int(os.getenv("DASHBOARD_PORT", "8080"))
        self.runner = web.AppRunner(self.app())
        await self.runner.setup()
        site = web.TCPSite(self.runner, host, port)
        await site.start()
        log.info("Dashboard on http://%s:%s", host, port)

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
        page = _read("login.html").replace("{{error}}", "")
        return web.Response(text=page, content_type="text/html")

    async def login_post(self, request: web.Request) -> web.StreamResponse:
        data = parse_qs(await request.text())
        secret = (data.get("secret") or [""])[0]
        if not hmac.compare_digest(secret, _secret()):
            page = _read("login.html").replace(
                "{{error}}", '<p class="err">Wrong secret.</p>'
            )
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
        cards = []
        for guild in self.bot.guilds:
            cards.append(
                f'<a class="card guild" href="/guild/{guild.id}">'
                f"<div><strong>{_e(guild.name)}</strong>"
                f'<div class="muted">{guild.id} · {guild.member_count} members</div></div>'
                f"<span>Open →</span></a>"
            )
        if not cards:
            cards.append('<div class="card">Bot is not in any servers yet.</div>')
        body = "<h1>Servers</h1><p class='muted'>Pick a guild to edit welcome, temp voice, and extra settings.</p>" + "".join(cards)
        return _page("Servers", body)

    async def system(self, request: web.Request) -> web.Response:
        self._need_auth(request)
        exts = "".join(f"<li><code>{_e(name)}</code></li>" for name in self.bot.extensions)
        user = self.bot.user
        body = f"""
        <h1>System</h1>
        <div class="card">
          <p>Logged in as <strong>{_e(user)}</strong> ({_e(user.id if user else "")})</p>
          <p>Database: <code>{_e(self.db.path)}</code></p>
          <p>Root: <code>{_e(ROOT)}</code></p>
          <p>Loaded cogs:</p>
          <ul>{exts}</ul>
          <form method="post" action="/system/reload">
            <button type="submit">Reload all cogs now</button>
          </form>
          <p class="muted">Saving a <code>cogs/*.py</code> file also reloads that cog automatically.</p>
        </div>
        """
        return _page("System", body)

    async def reload_cogs(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        errors = []
        for ext in list(self.bot.extensions):
            try:
                await self.bot.reload_extension(ext)
            except Exception as exc:
                errors.append(f"{ext}: {exc}")
        if errors:
            log.error("Manual reload errors: %s", errors)
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
        if isinstance(reactions, list):
            reactions_s = " ".join(str(x) for x in reactions)
        else:
            reactions_s = str(reactions or "")

        lobbies = await self.db.lobbies(guild_id)
        rooms = await self.db.rooms(guild_id)
        rules = await self.db.reaction_roles_in_guild(guild_id)
        events = await self.db.fetchall(
            """
            SELECT user_id, action, created_at FROM member_events
            WHERE guild_id = ? ORDER BY id DESC LIMIT 15
            """,
            (guild_id,),
        )

        lobby_rows = "".join(
            f"<tr><td>{row['lobby_id']}</td><td>{row['category_id']}</td></tr>"
            for row in lobbies
        ) or "<tr><td colspan='2'>None — use /tempvc setup</td></tr>"
        room_rows = "".join(
            f"<tr><td>{row['channel_id']}</td><td>{row['owner_id']}</td></tr>"
            for row in rooms
        ) or "<tr><td colspan='2'>No live rooms</td></tr>"
        rule_rows = "".join(
            f"<tr><td>{row['message_id']}</td><td>{_e(row['emoji'])}</td><td>{row['role_id']}</td></tr>"
            for row in rules
        ) or "<tr><td colspan='3'>None — use /rules post</td></tr>"
        event_rows = "".join(
            f"<tr><td>{row['user_id']}</td><td>{_e(row['action'])}</td><td>{_e(row['created_at'])}</td></tr>"
            for row in events
        ) or "<tr><td colspan='3'>No joins recorded yet</td></tr>"

        checked = "checked" if cfg.get("enabled") else ""
        one_room = "checked" if cfg.get("one_room_per_owner") else ""
        w_on = "checked" if welcome_enabled else ""
        dm_on = "checked" if welcome_dm else ""

        body = f"""
        <h1>{_e(name)}</h1>
        <p class="muted">{guild_id}</p>

        <div class="grid2">
          <form class="card" method="post" action="/guild/{guild_id}/tempvc">
            <h2>Temp voice</h2>
            <label><input type="checkbox" name="enabled" {checked}> Enabled</label>
            <label>Room name template</label>
            <input name="channel_name" value="{_e(cfg.get('channel_name') or TEMPVC['channel_name'])}">
            <label>User limit (0 = none)</label>
            <input name="user_limit" type="number" min="0" max="99" value="{_e(cfg.get('user_limit', 0))}">
            <label>Bitrate</label>
            <input name="bitrate" type="number" min="8000" value="{_e(cfg.get('bitrate', 64000))}">
            <label>Delete delay (seconds)</label>
            <input name="delete_delay_seconds" type="number" min="0" max="60" value="{_e(cfg.get('delete_delay_seconds', 2))}">
            <label><input type="checkbox" name="one_room_per_owner" {one_room}> One room per owner</label>
            <p><button type="submit">Save voice settings</button></p>
          </form>

          <form class="card" method="post" action="/guild/{guild_id}/welcome">
            <h2>Welcome</h2>
            <label><input type="checkbox" name="enabled" {w_on}> Enabled</label>
            <label>Channel ID</label>
            <input name="channel_id" value="{_e(welcome_channel)}">
            <label>Message template</label>
            <textarea name="message">{_e(welcome_message)}</textarea>
            <label>Welcome reactions (space-separated)</label>
            <input name="reactions" value="{_e(reactions_s)}">
            <label><input type="checkbox" name="dm_enabled" {dm_on}> Send a DM</label>
            <label>DM template</label>
            <textarea name="dm_message">{_e(welcome_dm_msg)}</textarea>
            <p><button type="submit">Save welcome</button></p>
          </form>
        </div>

        <div class="card">
          <h2>Lobbies</h2>
          <table><tr><th>Lobby channel</th><th>Category</th></tr>{lobby_rows}</table>
          <h2>Live rooms</h2>
          <table><tr><th>Room</th><th>Owner</th></tr>{room_rows}</table>
          <h2>Rules / reaction roles</h2>
          <table><tr><th>Message</th><th>Emoji</th><th>Role</th></tr>{rule_rows}</table>
          <p class="muted">Create or move the rules message with <code>/rules post</code> — the dashboard stores the binding, Discord has to send the embed.</p>
        </div>

        <div class="card">
          <h2>Recent joins / leaves</h2>
          <table><tr><th>User</th><th>Action</th><th>When (UTC)</th></tr>{event_rows}</table>
        </div>

        <form class="card" method="post" action="/guild/{guild_id}/setting">
          <h2>Raw setting</h2>
          <p class="muted">Writes any key into <code>guild_settings</code>. Use this for new modules.</p>
          <label>Key</label>
          <input name="key" placeholder="trivia.enabled">
          <label>Value (JSON or plain text)</label>
          <input name="value" placeholder="true">
          <p><button type="submit">Save key</button></p>
        </form>
        """
        q = request.rel_url.query.get("ok")
        flash = flash_ok(q) if q else ""
        return _page(name, body, flash)

    async def save_tempvc(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        guild_id = int(request.match_info["guild_id"])
        form = parse_qs(await request.text())
        enabled = "enabled" in form
        one = "one_room_per_owner" in form
        await self.db.set_tempvc(
            guild_id,
            enabled=enabled,
            channel_name=(form.get("channel_name") or [""])[0] or TEMPVC["channel_name"],
            user_limit=int((form.get("user_limit") or ["0"])[0] or 0),
            bitrate=int((form.get("bitrate") or ["64000"])[0] or 64000),
            delete_delay_seconds=int((form.get("delete_delay_seconds") or ["2"])[0] or 2),
            one_room_per_owner=one,
        )
        raise web.HTTPFound(f"/guild/{guild_id}?ok=Temp+voice+saved")

    async def save_welcome(self, request: web.Request) -> web.StreamResponse:
        self._need_auth(request)
        guild_id = int(request.match_info["guild_id"])
        form = parse_qs(await request.text())
        channel_raw = (form.get("channel_id") or [""])[0].strip()
        channel_id = int(channel_raw) if channel_raw.isdigit() else None
        reactions = [p for p in (form.get("reactions") or [""])[0].split() if p]
        await self.db.set_setting(guild_id, "welcome.enabled", "enabled" in form)
        await self.db.set_setting(guild_id, "welcome.channel_id", channel_id)
        await self.db.set_setting(guild_id, "welcome.message", (form.get("message") or [WELCOME_MESSAGE])[0])
        await self.db.set_setting(guild_id, "welcome.reactions", reactions or ["👋"])
        await self.db.set_setting(guild_id, "welcome.dm_enabled", "dm_enabled" in form)
        await self.db.set_setting(guild_id, "welcome.dm_message", (form.get("dm_message") or [WELCOME_DM])[0])
        raise web.HTTPFound(f"/guild/{guild_id}?ok=Welcome+saved")

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
        else:
            try:
                if raw.strip() and raw.strip().lstrip("-").isdigit():
                    value = int(raw.strip())
            except ValueError:
                value = raw
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
