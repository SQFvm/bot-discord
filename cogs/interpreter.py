import logging

import discord
from discord.ext import commands

import settings
from sqfvm_wrapper import SQFVMWrapper

logger = logging.getLogger('discord.' + __name__)


class Interpreter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.interpreter_enabled = True
        # Store the wrapper in the bot namespace to be able to access it from other cogs
        self.bot.sqfvm = SQFVMWrapper(settings.SQFVM_LIB_PATH)
        try:
            self.bot.sqfvm.load()
        except:
            # Continue working because you can later call "!rebuild" to get SQF-VM working again
            logger.exception('Could not load SQF-VM!')

    async def execute_sqf(self, code):
        if self.bot.sqfvm.ready():
            retval = await self.bot.sqfvm.call_sqf_async(code)
        else:
            retval = "SQF-VM not ready. Try again later"
        return retval

    async def execute_sqc(self, code):
        if self.bot.sqfvm.ready():
            retval = await self.bot.sqfvm.call_sqc_async(code)
        else:
            retval = "SQF-VM not ready. Try again later"
        return retval

    @staticmethod
    def escape_markdown(text):
        prefix = '```sqf\n'
        suffix = '```'
        ellipsis = '(...)'

        if text == '':
            return '```\n```'  # Otherwise, Discord treats "sqf" as the message contents

        retval = '{}{}{}'.format(prefix, text, suffix)
        if len(retval) > 2000:
            allowed_length = 2000 - len(ellipsis) - len(prefix) - len(suffix)
            text = text[:allowed_length] + ellipsis  # "longtexthere" -> "longte(...)"
            retval = '{}{}{}'.format(prefix, text, suffix)

        return retval

    def strip_mentions_and_markdown(self, message, strip_command_marker=False):
        content = message.content.strip()

        if strip_command_marker and (content.startswith('!sqf') or content.startswith('!sqc')):
            content = content[5:]

        if self.bot.user.id in message.raw_mentions:
            content = content.replace('<@!{}>'.format(self.bot.user.id), '')

        if (content.startswith('```sqf') or content.startswith('```sqc')) and content.endswith('```'):
            content = content[6:-3]

        return content

    @commands.command()
    async def sqf(self, ctx):
        """
        Execute SQF code and return the resulting value

        Alternatively, for the same effect you can also:
        - Mention the bot, when pasting your code
        - Write a DM to the bot
        - Enclose your message in an ``'sqf block
          if the channel name starts with "sqf"
        """
        code_to_execute = self.strip_mentions_and_markdown(ctx.message, strip_command_marker=True)

        async with ctx.typing():
            result = await self.execute_sqf(code_to_execute)
        await ctx.channel.send(self.escape_markdown(result))

    @commands.command()
    async def sqc(self, ctx):
        """
        Execute SQC code and return the resulting value

        Alternatively, for the same effect you can also:
        - Mention the bot, when pasting your code
        - Write a DM to the bot
        - Enclose your message in an ``'sqc block
          if the channel name starts with "sqc"
        """
        code_to_execute = self.strip_mentions_and_markdown(ctx.message, strip_command_marker=True)

        async with ctx.typing():
            result = await self.execute_sqc(code_to_execute)
        await ctx.channel.send(self.escape_markdown(result))

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Check if this message needs to be sqf-interpreted
        Ignore messages from bots or valid commands
        Interpret if the message:
        - Is in a DM channel
        - Mentions the bot
        - Is in a channel named "sqf..." and is in an sqf block
        """

        # Ignore messages coming from bots
        if message.author.bot:
            return

        # If this is a valid command, ignore this message
        ctx = await self.bot.get_context(message)
        if ctx.command:
            return

        code_to_execute = None
        function_to_execute = self.execute_sqf  # Default

        if self.bot.user.id in message.raw_mentions:
            code_to_execute = self.strip_mentions_and_markdown(message)

        elif type(message.channel) is discord.DMChannel:  # Always interpret when DM
            code_to_execute = self.strip_mentions_and_markdown(message)

        # Don't use elif here because the ```sqX may override the language type to execute
        if message.channel.name.startswith('sqf') or message.channel.name.startswith('sqc'):
            if message.content.startswith('```sqf'):
                code_to_execute = self.strip_mentions_and_markdown(message)
                function_to_execute = self.execute_sqf
            elif message.content.startswith('```sqc'):
                code_to_execute = self.strip_mentions_and_markdown(message)
                function_to_execute = self.execute_sqc

        if code_to_execute:
            async with message.channel.typing():
                sqf_result = await function_to_execute(code_to_execute)
            await message.channel.send(self.escape_markdown(sqf_result))


def setup(bot):
    bot.add_cog(Interpreter(bot))
