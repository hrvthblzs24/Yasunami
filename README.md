# Yasunami

Discord slash bot: join-to-create voice rooms, welcome messages, a rules reaction-role, and an SQLite database built to hold minigame stats later.

Repo: https://github.com/hrvthblzs24/Yasunami

Everything persistent lives in `data/bot.db`. There is no JSON config store.

## Features

- Join-to-create lobby to personal voice room named after the user, deleted when empty
- Owner room controls (`/vc rename`, lock, limit, kick, transfer, claim)
- Welcome message + reactions + optional DM
- Rules message: react to get the Member role
- SQLite users / joins / settings / stats
- Example minigame `/rps` writing into `stats`
- Local dashboard at http://127.0.0.1:8080
- Hot reload for cogs

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

`.env` only needs `DISCORD_TOKEN`. Enable Server Members Intent. Invite with `bot` and `applications.commands`.

## First commands

```
/rules post channel:#rules role:@Member emoji:\u2705
/welcome setup channel:#welcome
/tempvc setup
```
