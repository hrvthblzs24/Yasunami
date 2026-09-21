# Server bot

Discord slash bot: join-to-create voice rooms, welcome messages, a rules reaction-role, and an SQLite database built to hold minigame stats later.

Everything persistent lives in `data/bot.db`. There is no JSON config store.

## Features

- Join-to-create lobby → personal voice room named after the user → delete when empty
- Owner room controls (`/vc rename`, lock, limit, kick, transfer, claim)
- Welcome message + reactions + optional DM
- Rules message: react to get the Member role
- SQLite users / joins / settings / stats
- Example minigame `/rps` writing into `stats`

## Setup (Windows)

```bat
cd tempvc-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env
python bot.py
```

`.env` only needs:

```
DISCORD_TOKEN=your_bot_token
```

Developer Portal:

1. Enable **Server Members Intent**
2. Invite with scopes `bot` **and** `applications.commands`
3. Permissions: Administrator is easiest while testing

```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=8&scope=bot%20applications.commands
```

Put the bot role at the top of the role list so it can assign Member.

## First commands in Discord

```
/rules post channel:#rules role:@Member emoji:✅
/welcome setup channel:#welcome
/tempvc setup
```

`/rules post` sends an embed, adds ✅, and stores the binding in SQLite. Anyone who reacts gets `@Member`. Removing the reaction removes the role.

If you already posted rules by hand:

```
/rules bind message_id:123456789 channel:#rules role:@Member emoji:✅
```

## Commands

### Rules

| Command | What it does |
| --- | --- |
| `/rules post` | Post rules + attach reaction role |
| `/rules bind` | Attach a role to an existing message |
| `/rules clear` | Stop listening on a message |
| `/rules status` | List bindings |

### Welcome

| Command | What it does |
| --- | --- |
| `/welcome setup` | Channel, template, reaction |
| `/welcome reactions` | Emojis on the welcome message |
| `/welcome toggle` / `/welcome dm` | On/off |
| `/welcome test` | Preview |
| `/profile` | Join count + stats |

### Temp voice

| Command | What it does |
| --- | --- |
| `/tempvc setup` / `bind` / `unbind` / `config` | Admin |
| `/vc rename` `limit` `lock` `unlock` `kick` `transfer` `claim` | Room owner |

## Database

File: `data/bot.db`

| Table | Purpose |
| --- | --- |
| `users` | Discord user cache |
| `members` | Per-server join count / present flag |
| `member_events` | Join/leave history |
| `guild_settings` | Feature settings (`welcome.*`, `tempvc.*`, `rules.*`) |
| `stats` | `(guild, user, game, key) → number` |
| `tempvc_lobbies` | Join-to-create lobby channels |
| `tempvc_rooms` | Live personal rooms + owner |
| `reaction_roles` | Rules message → emoji → role |

New game:

```python
await bot.db.add_stat(guild.id, user.id, "trivia", "wins", 1)
top = await bot.db.leaderboard(guild.id, "trivia", "wins", 10)
await bot.db.set_setting(guild.id, "trivia.enabled", True)
```

Copy `cogs/rps.py`, add the module name to `EXTENSIONS` in `bot.py`.

## Layout

```
tempvc-bot/
├── bot.py
├── requirements.txt
├── cogs/
│   ├── tempvc.py
│   ├── commands.py
│   ├── welcome.py
│   ├── rules.py
│   ├── profile.py
│   └── rps.py
├── core/
│   ├── database.py
│   ├── defaults.py
│   └── ...
└── data/bot.db
```

## Hot reload

Leave `HOT_RELOAD=true` in `.env`. Saving a file under `cogs/` reloads that cog in about a second. HTML in `web/templates/` is read on every request. Changing `bot.py` still needs a process restart.

## Dashboard

Starts with the bot at [http://127.0.0.1:8080](http://127.0.0.1:8080).

1. Set `DASHBOARD_SECRET` in `.env` (do not leave `change-me` if you bind to `0.0.0.0`)
2. Open the URL, enter that secret
3. Pick a server and edit temp voice, welcome, or any raw `guild_settings` key

It binds to `127.0.0.1` by default so only your machine can open it.
