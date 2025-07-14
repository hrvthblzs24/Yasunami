import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from psnawp_api import PSNAWP
from psnawp_api.models.search.games_search_datatypes import SearchDomain, GameSearchResultItem, GameProductResult
from conf.embeds import PS_GAME_RESULT


async def search_psgame(bot : commands.bot, api : PSNAWP, query : tuple):
    search : GameSearchResultItem = api.search(search_query=" ".join(query), search_domain=SearchDomain.FULL_GAMES)
    i = 0
    for x in search:
        if i == 0:
            i += 1
            print(x["result"]["invariantName"])
            embed = PS_GAME_RESULT(x["result"])
            return embed
        
        else: break
