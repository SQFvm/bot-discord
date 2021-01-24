import asyncio
import logging

from discord.ext import commands

import checks
from discord_base import get_bots

logger = logging.getLogger('discord.' + __name__)


class Restart(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @checks.only_admins()
    async def restart(self, ctx):
        """
        Restart all the bots.
        This allows the bots to update and to restart with the new source code.
        If the bots take more than half a minute to restart it means that they have probably crashed.
        """

        logger.info('Restarting by request of: {}'.format(str(ctx.author)))

        await ctx.channel.send('Restarting discord bots...')
        for bot in get_bots():
            await bot.logout()

        loop = asyncio.get_event_loop()
        loop.stop()

    @restart.error
    async def restart_error(self, ctx, error):
        pass


def setup(bot):
    bot.add_cog(Restart(bot))
