from discord import Embed, Color
from dotenv import load_dotenv
from discord.ext import commands
from psnawp_api.models.search.games_search_datatypes import GameProductResult
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
def PS_GAME_RESULT(result : GameProductResult):
    print("start")
    final = Embed(
    title=result["invariantName"], 
    description=f"""
[🎮]    {", ".join(result['platforms'])}

""",
    color=Color.blurple(),
)
    final.set_image(url=result["media"][0]["url"])
    final.set_author(name="Visit on PlayStation Store",icon_url=result["media"][1]["url"], url=f"https://store.playstation.com/en-tw/concept/{str(result["id"])}")
    return final
def NEW_GAMEPASS_GAME(title):
    return Embed(
    title=title, 
    description=f"🎮| Új játék az Xbox Gamepass-en!",
    color=Color.green(),
)