TEMPVC = {
    "enabled": True,
    "channel_name": "{display_name}'s Room",
    "lobby_name": "➕ Join to Create",
    "category_name": "Voice Rooms",
    "user_limit": 0,
    "bitrate": 64000,
    "one_room_per_owner": True,
    "delete_delay_seconds": 2,
    "lobby_user_limit": 1,
    "owner_permissions": [
        "manage_channels",
        "mute_members",
        "deafen_members",
        "move_members",
        "connect",
        "speak",
        "stream",
        "use_voice_activation",
    ],
}

WELCOME_MESSAGE = "{mention} welcome to **{server}** — you are member #{member_count}."
WELCOME_DM = "Hey {user}, welcome to {server}!"

RULES_BODY = (
    "By reacting below you agree to follow the server rules and receive the member role.\n\n"
    "1. Be respectful. No harassment, hate, or slurs.\n"
    "2. No spam, ads, or scam links.\n"
    "3. Keep channels on-topic.\n"
    "4. Follow Discord's Terms of Service.\n"
    "5. Staff decisions stand — open a ticket if you need to appeal.\n\n"
    "React with {emoji} to accept and unlock the server."
)
