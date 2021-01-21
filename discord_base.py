import asyncio
import inspect
import logging
import time

from discord.ext import commands

logger = logging.getLogger('discord.' + __name__)
bots = []


def get_bots():
    return bots


class BotBase(commands.Bot):
    def __init__(self, *args, **kwargs):
        self.periodic_commands = []
        super().__init__(*args, **kwargs)

        # Load commands and periodic commands declared in cogs
        self.load_extensions()

        # Load periodic commands declared directly in the class
        self.load_extra_commands(self)

        # Add global check to ignore commands sent by other bots
        # Will raise exceptions on those commands in the bot(s)
        async def ignore_other_bots(ctx):
            return not ctx.message.author.bot
        self.add_check(ignore_other_bots)

    async def on_ready(self):
        logger.info('Logged in as')
        logger.info(self.user.name)
        logger.info(self.user.id)
        logger.info('------')

        while not self.ws:
            await asyncio.sleep(0.1)

        # Set the bot name
        if self.user.name != self.bot_data['name']:
            await self.user.edit(username=self.bot_data['name'])

    def load_extensions(self):
        for extension in self.startup_extensions:
            try:
                self.load_extension(extension)
            except Exception as e:
                exc = '{}: {}'.format(type(e).__name__, e)
                logger.error('Failed to load extension %s\n%s', extension, exc)

    def add_periodic_command(self, member, interval):
        logger.info('Registering periodic command every {} seconds: {}'.format(
            interval, member.__name__))
        self.periodic_commands.append((member, interval))

    def load_extra_commands(self, object):
        members = inspect.getmembers(object)
        for name, member in members:
            registered_periodic_command_interval = getattr(member, '_registered_periodic_command_interval', None)
            if registered_periodic_command_interval:
                self.add_periodic_command(member, registered_periodic_command_interval)

    def add_cog(self, cog):
        retval = super().add_cog(cog)
        self.load_extra_commands(cog)

        return retval

    async def periodic(self, function, interval):
        await self.wait_until_ready()

        while not self.ws:
            await asyncio.sleep(1)

        while True:
            start = time.time()
            try:
                await function()
            except Exception:
                import traceback
                traceback.print_exc()

            end = time.time()
            # adjust interval
            adjusted_interval = max(interval - end + start, 0)
            await asyncio.sleep(adjusted_interval)


# Decorator that marks a given bot function as a periodic command to be
# executed every interval seconds.
def periodic_command(interval):
    def real_decorator(function):
        def wrapper(*args, **kwargs):
            return function(*args, **kwargs)

        wrapper._registered_periodic_command_interval = interval
        return wrapper
    return real_decorator


def create_bot(cls, arg):
    """Utility function for creating a bot and registering its periodic functions."""
    tasks = []
    bots = get_bots()

    bot = cls(arg)
    bots.append(bot)
    bot.loop.create_task(bot.start(bot.bot_data['bot_token']))

    # Register periodic functions
    for (function, registered_periodic_command_interval) in bot.periodic_commands:
        logger.info('Creating future: {}'.format(function))
        task = bot.loop.create_task(bot.periodic(function, registered_periodic_command_interval))
        tasks.append(task)

    return tasks
