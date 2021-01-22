import logging

import discord
from discord.ext import commands

logger = logging.getLogger('discord.' + __name__)


class InterpreterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.interpreter_enabled = True

    async def execute_sqf(self, code):
        return '[DUMMY RETURN VALUE]'

    def strip_mentions_and_markdown(self, message):
        content = message.content.strip()

        if self.bot.user.id in message.raw_mentions:
            content = content.replace('<@!{}>'.format(self.bot.user.id), '')

        if content.startswith('```sqf') and content.endswith('```'):
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
        code_to_execute = self.strip_mentions_and_markdown(ctx)

        async with ctx.typing():
            sqf_result = await self.execute_sqf(code_to_execute)
        await ctx.channel.send('```sqf\n{}```'.format(sqf_result))

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore messages coming from bots
        if message.author.bot:
            return

        # If this is a valid command, ignore this message
        ctx = await self.bot.get_context(message)
        if ctx.command:
            return

        code_to_execute = None

        if self.bot.user.id in message.raw_mentions:
            code_to_execute = self.strip_mentions_and_markdown(message)

        elif type(message.channel) is discord.DMChannel:  # Always interpret when DM
            code_to_execute = self.strip_mentions_and_markdown(message)

        elif message.channel.name.startswith('sqf') and message.content.startswith('```sqf'):
            code_to_execute = self.strip_mentions_and_markdown(message)

        if code_to_execute:
            async with message.channel.typing():
                sqf_result = await self.execute_sqf(code_to_execute)
            await message.channel.send('```sqf\n{}```'.format(sqf_result))


def setup(bot):
    bot.add_cog(InterpreterCog(bot))
