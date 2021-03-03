import logging

import discord
from discord.ext import commands

# import checks
from discord_base import periodic_command
from modules.discord_utils import escape_markdown
from modules.mediawiki import get_list, get_page, parse_mediawiki_textarea, SQFCommand

logger = logging.getLogger('discord.' + __name__)


class Wiki(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.commands = {}

    @periodic_command(3600)
    async def fetch_commands(self):
        logger.info('Fetching list of commands...')
        self.commands = await get_list()
        logger.info('Fetched %d commands', len(self.commands))

    # def add_syntax_field(self, embed, syntax, parameters, return_value):
    #     embed.add_field(name='-------------',
    #                     value=f'**Syntax:**\n'
    #                           f'**Parameters:**\n' + '\n' * (len(parameters) - 1) +
    #                           f'**Return value:** {return_value}',
    #                     inline=True)
    #
    #     embed.add_field(name='-------------',
    #                     value=f'{syntax}\n' + '\n'.join(parameters) + f'\n{return_value}',
    #                     inline=True)

    # https://www.w3schools.com/charsets/ref_html_entities_e.asp

    # def add_syntax_field(self, embed, syntax, parameters, return_value):
    #     embed.add_field(name='Syntax:', value=syntax, inline=False)
    #     embed.add_field(name='Parameters:', value='\n'.join(parameters), inline=False)
    #     embed.add_field(name='Return value:', value=return_value, inline=False)

    def add_syntax_field(self, embed, syntax, parameters, return_value):
        parameters_text = ('**Parameters:**   ' + '\n      '.join(parameters) if len(parameters) > 1 else
                           '**Parameters:** ' + '\n'.join(parameters))
        embed.add_field(name='-------------',
                        value=f'**Syntax:**     {syntax}\n{parameters_text}\n**Return value:** {return_value}',
                        inline=False)

    @commands.command()
    async def biki(self, ctx, name: str):
        """
        Get the description of a command from the Biki
        """
        try:
            command_url_part = self.commands[name]
        except KeyError:
            await ctx.channel.send('Unknown command!')
            return

        async with ctx.typing():
            page_contents = await get_page(command_url_part.replace('/wiki/', ''))
            template = parse_mediawiki_textarea(page_contents)
            sqf_command = SQFCommand(name, template)

        embed = discord.Embed(title=name, url=f'https://community.bistudio.com/{command_url_part}',
                              description=sqf_command.description)

        await ctx.channel.send(embed=embed)

    @biki.error
    async def biki_error(self, ctx, error):
        await ctx.channel.send(error)

    async def _biki_full(self, ctx, name: str, to_sqc=False):
        try:
            command_url_part = self.commands[name]
        except KeyError:
            await ctx.channel.send('Unknown command!')
            return

        async with ctx.typing():
            page_contents = await get_page(command_url_part.replace('/wiki/', ''))
            template = parse_mediawiki_textarea(page_contents)
            sqf_command = SQFCommand(name, template)

        embed = discord.Embed(title=name, url=f'https://community.bistudio.com/{command_url_part}',
                              description=sqf_command.description)
        # embed.set_author(name=sqf_command.type)#, url="asd", icon_url="asd")

        self.add_syntax_field(embed, sqf_command.syntax, sqf_command.parameters, sqf_command.return_value)
        for syntax, parameters, return_value in zip(
                sqf_command.alt_syntax, sqf_command.alt_parameters, sqf_command.alt_return_value):
            self.add_syntax_field(embed, syntax, parameters, return_value)

        interpreter = self.bot.get_cog('Interpreter')

        for i, example in enumerate(sqf_command.examples):
            if interpreter and to_sqc:
                example = await interpreter.execute_sqf2sqc(example)
            embed.add_field(name='Example:' if i == 0 else f'Example {i + 1}:',
                            value=escape_markdown(example, 'sqf'),
                            inline=False)

        embed.set_footer(text=f'See also: {sqf_command.see_also}\nGroups: {",".join(sqf_command.command_groups)}')
        await ctx.channel.send(embed=embed)

    @commands.command()
    async def biki_full(self, ctx, name: str):
        """
        Get the full page of a command from the Biki
        """
        await self._biki_full(ctx, name)

    @biki_full.error
    async def biki_full_error(self, ctx, error):
        await ctx.channel.send(error)

    @commands.command()
    async def biki_sqc(self, ctx, name: str):
        """
        Get the full page of a command from the Biki for SQC
        """
        await self._biki_full(ctx, name, to_sqc=True)

    @biki_sqc.error
    async def biki_sqc_error(self, ctx, error):
        await ctx.channel.send(error)


def setup(bot):
    bot.add_cog(Wiki(bot))


