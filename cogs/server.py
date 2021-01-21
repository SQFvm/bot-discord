import logging

from discord.ext import commands

logger = logging.getLogger('discord.' + __name__)


class ServerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(ServerCog(bot))
