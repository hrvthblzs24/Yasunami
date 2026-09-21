from __future__ import annotations

import logging
import os
from pathlib import Path

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from core.database import Database
from core.reloader import HotReloader
from web.app import start_dashboard

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("yasunami")

EXTENSIONS = (
    "cogs.tempvc",
    "cogs.commands",
    "cogs.welcome",
    "cogs.rules",
    "cogs.profile",
    "cogs.rps",
)

HEARTS = ("🩷", "🧡", "🧡", "💛", "💚", "💙", "💜", "❤️")
