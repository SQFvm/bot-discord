#!/usr/bin/env python
import logging

from discord_base import create_bot, get_bots

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

import asyncio
import settings
from bots import SQFBot


def wakeup():
    """Dummy loop that allows using Ctrl+C in Windows"""
    loop = asyncio.get_event_loop()
    loop.call_later(0.3, wakeup)


tasks = []


async def on_shutdown():
    global tasks
    logger.info('Stopping bot...')
    for task in tasks:
        task.cancel()

    for bot in get_bots():
        logger.info('Closing client')
        await bot.logout()


def run_discord_bots():
    global tasks

    tasks.extend(create_bot(SQFBot, settings.SQF_BOT))


def main():
    loop = asyncio.get_event_loop()
    wakeup()

    try:
        run_discord_bots()
        loop.run_forever()

    except KeyboardInterrupt:
        loop.run_until_complete(on_shutdown())

    finally:
        loop.close()


if __name__ == '__main__':
    main()
