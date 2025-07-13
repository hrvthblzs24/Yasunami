from discord import Embed, Color
from dotenv import load_dotenv
from discord.ext import commands
import os

load_dotenv()

def CURRENTLY_PLAYING_ON_RADIO(title, folder):
    return Embed(
    title="MILØX™ 24/7", 
    description=f"**Zenecím:** {title}\n**Lejátszási lista:** {folder}",
    color=Color.blurple(),
)

def GET_KNOWN_CARD(bot : commands.Bot):
    final = Embed (
        title="Elérhetőségek",
        description="""
**--[ MAIN ]--**
[✉️] <mailto:hrvthblzs24@icloud.com>
[☁️] <https://soundcloudcom/hrvthblzs24>
[💾] <https://github.com/tcgmilan>

**--[ MILØX ]--**
[✉️] <mailto:mail.milox@gmail.com>
[☁️] <https://soundcloud.com/miloxmusic>
[🌐] <https://solo.to/milox-hun>
        """,
        color=Color.blurple(),
    )
    final.set_author(name="MILØX™",url="https://solo.to/miloxmusic", icon_url=bot.get_user(int(os.getenv("MILOX_ID"))).display_avatar.url)
    return final