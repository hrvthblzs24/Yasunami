# Yasunami

All-in-one Discord bot by **MILOX**.

Temp voice rooms, welcome messages, rules reaction-roles, member tracking, a local dashboard, and room for minigames — one process, one SQLite file.

Repo: https://github.com/hrvthblzs24/Yasunami

## Features

- Join-to-create lobby → personal voice room named after the user → delete when empty
- Room owner controls (`/vc rename`, lock, limit, kick, transfer, claim)
- Welcome message + reactions + optional DM
- Rules message: react to receive the Member role
- SQLite users, joins, settings, and game stats
- Example minigame `/rps`
- Dashboard at http://127.0.0.1:8080
- Hot-reload when you save a cog
- Rich presence: `Yasunami | Made by MILOX, with` plus a heart that cycles every second
  🩷 🧡 🧠 💛 💚 💙 💜 ❤️

## Setup (Windows)

```bat
git clone https://github.com/hrvthblzs24/Yasunami.git
cd Yasunami
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env
python bot.py
```

`.env` needs `DISCORD_TOKEN`. Enable **Server Members Intent**. Invite with scopes `bot` and `applications.commands`.

## First commands

```
/rules post channel:#rules role:@Member emoji:✅
/welcome setup channel:#welcome
/tempvc setup
```

## Layout

```
Yasunami/
├── bot.py
├── requirements.txt
├── cogs/
├── core/
├── web/
└── data/bot.db
```

Persistent data is only `data/bot.db`. Do not commit `.env`.
