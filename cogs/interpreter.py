import logging

import discord
from discord.ext import commands

import settings
from modules.discord_utils import escape_markdown
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

    async def execute_sqf2sqc(self, code):
        if self.bot.sqfvm.ready():
            retval = await self.bot.sqfvm.call_sqf2sqc_async(code)
        else:
            retval = "SQF-VM not ready. Try again later"
        return retval

    async def execute_assembly(self, code):
        if self.bot.sqfvm.ready():
            retval = await self.bot.sqfvm.call_assembly_async(code)
        else:
            retval = "SQF-VM not ready. Try again later"
        return retval

    async def execute_preprocess(self, code):
        if self.bot.sqfvm.ready():
            retval = await self.bot.sqfvm.call_preprocess_async(code)
        else:
            retval = "SQF-VM not ready. Try again later"
        return retval

    def strip_mentions_and_markdown(self, message, strip_command_marker=False):
        content = message.content.strip()

        if strip_command_marker:
            if content.startswith('!sqf2sqc'):
                content = content[9:]
            elif content.startswith('!sqf') or content.startswith('!sqc'):
                content = content[5:]
            elif content.startswith('!assembly'):
                content = content[10:]
            elif content.startswith('!preprocess'):
                content = content[12:]

        if self.bot.user.id in message.raw_mentions:
            content = content.replace('<@!{}>'.format(self.bot.user.id), '')

        if content.startswith('```sqf2sqc') and content.endswith('```'):
            content = content[10:-3]
        elif (content.startswith('```sqf') or content.startswith('```sqc')) and content.endswith('```'):
            content = content[6:-3]
        elif content.startswith('```assembly') and content.endswith('```'):
            content = content[11:-3]
        elif content.startswith('```preprocess') and content.endswith('```'):
            content = content[13:-3]

        return content

    @commands.command()
    async def sqf(self, ctx):
        """
        Execute SQF code and return the resulting value

        Alternatively, for the same effect you can also:
        - Mention the bot, when pasting your code
        - Write a DM to the bot
        - Enclose your message in an ``'sqf block
          if the channel name starts with "sqf" or "sqc"
        """
        code_to_execute = self.strip_mentions_and_markdown(ctx.message, strip_command_marker=True)

        async with ctx.typing():
            result = await self.execute_sqf(code_to_execute)
        await ctx.channel.send(escape_markdown(result, language='sqf'))

    @commands.command()
    async def sqc(self, ctx):
        """
        Execute SQC code and return the resulting value

        Alternatively, for the same effect you can also:
        - Mention the bot, when pasting your code
        - Write a DM to the bot
        - Enclose your message in an ``'sqc block
          if the channel name starts with "sqf" or "sqc"
        """
        code_to_execute = self.strip_mentions_and_markdown(ctx.message, strip_command_marker=True)

        async with ctx.typing():
            result = await self.execute_sqc(code_to_execute)
        await ctx.channel.send(escape_markdown(result, language='sqf'))

    @commands.command()
    async def sqf2sqc(self, ctx):
        """
        Parse SQF and transpile the code to SQC

        Alternatively, for the same effect you can also:
        - Mention the bot, when pasting your code
        - Write a DM to the bot
        - Enclose your message in an ``'sqf2sqc block
          if the channel name starts with "sqf" or "sqc"
        """
        code_to_execute = self.strip_mentions_and_markdown(ctx.message, strip_command_marker=True)

        async with ctx.typing():
            result = await self.execute_sqf2sqc(code_to_execute)
        await ctx.channel.send(escape_markdown(result, language='sqf'))

    @commands.command()
    async def assembly(self, ctx):
        """
        Execute SQF assembly and return the resulting value

        Alternatively, for the same effect you can also:
        - Write a DM to the bot
        - Enclose your message in an ``'assembly block
          if the channel name starts with "sqf" or "sqc"
        """
        code_to_execute = self.strip_mentions_and_markdown(ctx.message, strip_command_marker=True)

        async with ctx.typing():
            result = await self.execute_assembly(code_to_execute)
        await ctx.channel.send(escape_markdown(result, language='sqf'))

    @commands.command()
    async def preprocess(self, ctx):
        """
        Preprocess code and return the result

        Alternatively, for the same effect you can also:
        - Write a DM to the bot
        - Enclose your message in an ``'preprocess block
          if the channel name starts with "sqf" or "sqc"
        """
        code_to_execute = self.strip_mentions_and_markdown(ctx.message, strip_command_marker=True)

        async with ctx.typing():
            result = await self.execute_preprocess(code_to_execute)
        await ctx.channel.send(escape_markdown(result, language='sqf'))

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
            if message.content.startswith('```sqf2sqc'):
                code_to_execute = self.strip_mentions_and_markdown(message)
                function_to_execute = self.execute_sqf2sqc
            elif message.content.startswith('```sqf'):
                code_to_execute = self.strip_mentions_and_markdown(message)
                function_to_execute = self.execute_sqf
            elif message.content.startswith('```sqc'):
                code_to_execute = self.strip_mentions_and_markdown(message)
                function_to_execute = self.execute_sqc
            elif message.content.startswith('```assembly'):
                code_to_execute = self.strip_mentions_and_markdown(message)
                function_to_execute = self.execute_assembly
            elif message.content.startswith('```preprocess'):
                code_to_execute = self.strip_mentions_and_markdown(message)
                function_to_execute = self.execute_preprocess

        if code_to_execute:
            async with message.channel.typing():
                sqf_result = await function_to_execute(code_to_execute)
            await message.channel.send(escape_markdown(sqf_result, language='sqf'))


def setup(bot):
    bot.add_cog(Interpreter(bot))
