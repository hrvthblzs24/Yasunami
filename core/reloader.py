from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord.ext import commands

from core.paths import ROOT

log = logging.getLogger("bot.reloader")

WATCH_DIRS = (ROOT / "cogs", ROOT / "web", ROOT / "core")
WATCH_GLOBS = ("*.py", "*.html", "*.css")


def _snapshot() -> dict[Path, float]:
    out: dict[Path, float] = {}
    for folder in WATCH_DIRS:
        if not folder.exists():
            continue
        for pattern in WATCH_GLOBS:
            for path in folder.rglob(pattern):
                if path.name == "__init__.py" and path.parent in {ROOT / "cogs", ROOT / "web", ROOT / "core"}:
                    continue
                try:
                    out[path] = path.stat().st_mtime
                except OSError:
                    continue
    bot_py = ROOT / "bot.py"
    if bot_py.exists():
        out[bot_py] = bot_py.stat().st_mtime
    return out


class HotReloader:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._task: asyncio.Task | None = None
        self._last = _snapshot()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = self.bot.loop.create_task(self._run(), name="hot-reload")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run(self) -> None:
        log.info("Hot reload watching %s", ", ".join(str(p) for p in WATCH_DIRS))
        while not self.bot.is_closed():
            await asyncio.sleep(1.0)
            current = _snapshot()
            changed = [
                path
                for path, mtime in current.items()
                if path not in self._last or self._last[path] != mtime
            ]
            self._last = current
            if not changed:
                continue
            await self._handle(changed)

    async def _handle(self, changed: list[Path]) -> None:
        cogs_changed: list[str] = []
        core_changed = False
        web_py_changed = False
        bot_py_changed = False

        for path in changed:
            rel = path.relative_to(ROOT)
            log.info("File changed: %s", rel)
            parts = rel.parts
            if parts[0] == "cogs" and path.suffix == ".py":
                cogs_changed.append(f"cogs.{path.stem}")
            elif parts[0] == "core" and path.suffix == ".py":
                core_changed = True
            elif parts[0] == "web" and path.suffix == ".py":
                web_py_changed = True
            elif path.name == "bot.py":
                bot_py_changed = True
            # html/css are read from disk per request — no action

        if bot_py_changed:
            log.warning("bot.py changed — hot reload cannot apply that. Restart the process.")

        if core_changed:
            log.warning(
                "core/ changed — database/helpers stay in memory. "
                "Cogs will reload; restart if the schema or Database class changed."
            )
            for ext in list(self.bot.extensions):
                await self._reload(ext)
        else:
            for ext in dict.fromkeys(cogs_changed):
                if ext in self.bot.extensions or ext.replace("cogs.", "") :
                    await self._reload(ext)

        if web_py_changed and hasattr(self.bot, "restart_dashboard"):
            try:
                await self.bot.restart_dashboard()
                log.info("Dashboard web server reloaded")
            except Exception:
                log.exception("Dashboard reload failed")

    async def _reload(self, ext: str) -> None:
        try:
            if ext in self.bot.extensions:
                await self.bot.reload_extension(ext)
            else:
                await self.bot.load_extension(ext)
            log.info("Reloaded %s", ext)
        except Exception:
            log.exception("Failed to reload %s", ext)
            if ext not in self.bot.extensions:
                try:
                    await self.bot.load_extension(ext)
                    log.info("Recovered %s with a fresh load", ext)
                except Exception:
                    log.exception("Could not recover %s", ext)
