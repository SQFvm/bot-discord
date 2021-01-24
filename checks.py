from discord.ext import commands

import settings


# def frl_team_or_contributor():
#     async def predicate(ctx):
#         if ctx.guild is None:
#             return False  # Can't check role for DMs
#
#         roles = [r.id for r in ctx.author.roles]
#         allowed_roles = set([settings.FRL_TEAM_GROUP_ID, settings.CONTRIBUTOR_GROUP_ID])
#
#         return bool(allowed_roles.intersection(roles))
#     return commands.check(predicate)


def only_admins():
    async def predicate(ctx):
        return ctx.author.id in settings.ADMINS
    return commands.check(predicate)


def only_DM():
    async def predicate(ctx):
        return ctx.guild is None
    return commands.check(predicate)


def bot_mentioned():
    async def predicate(ctx):
        return ctx.bot.user.id in ctx.message.raw_mentions
    return commands.check(predicate)
