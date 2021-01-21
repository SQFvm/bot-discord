import asyncio
import logging
import subprocess

from discord.ext import commands

import checks
import settings

logger = logging.getLogger('discord.' + __name__)


class FancyProgress:
    def __init__(self):
        self.messages = []

    def next_state(self, state):
        self.messages.append(state)
        return self  # So that we can chain calls

    def __str__(self):
        return '```\n' + '\n'.join(self.messages) + '```'

class RebuilderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def git_pull(self, branch='master'):
        full_branch = branch if '/' in branch else 'origin/{}'.format(branch)
        git_command = ['git', '-C', settings.VMPATH]

        # Note: this is the 100% correct way of updating a repository
        update_commands = [
            git_command + ['reset', '--hard'],
            git_command + ['fetch', '--all'],
            git_command + ['checkout', branch],
            git_command + ['reset', '--hard', full_branch],
            git_command + ['pull'],
        ]

        for command in update_commands:
            logger.info('Running: %s', ' '.join(command))
            subprocess.run(command, check=True)

    def build_sqfvm(self):
        import time
        time.sleep(5)

    @commands.command()
    @checks.only_admins()
    async def rebuild(self, ctx):
        """Update and rebuild SQFvm"""
        progress = FancyProgress()

        async with ctx.typing():
            message = await ctx.channel.send(progress.next_state('Freeing current...'))
            # TODO: disable SQFvm

            await message.edit(content=progress.next_state('Pulling changes...'))
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.git_pull)
            except Exception as e:
                logger.exception('%s', e)
                await message.edit(content=progress.next_state('Error: ' + str(e)))
                return

            # TODO: build
            await message.edit(content=progress.next_state('Building...'))
            await asyncio.get_event_loop().run_in_executor(None, self.build_sqfvm)
            # TODO: Reload everything

        await ctx.channel.send('SQFvm has been rebuilt!')


def setup(bot):
    bot.add_cog(RebuilderCog(bot))
