# Set up your bots

* Copy `settings\local_sample.py` to `settings\local.py`
* Open `settings\local.py` and override the settings from `base.py` by setting
new values for all the variables that you want to override.
The absolute minimum would be the token in `SQF_BOT['bot_token']`.
See below on how to obtain it.

Create your own testing Discord channel, and follow these instructions to
create your own test bot:

https://github.com/reactiflux/discord-irc/wiki/Creating-a-discord-bot-&-getting-a-token

Once you have created it, put its token in the `bot_token:` field.
You're now ready to run the bot.

# Quick setup

    pip install -r requirements\base.txt

# Start the bots

    python main.py

# Server deployment

Just run `start_production.sh`

# Additional notes

This will run the bots with the settings taken from `settings.local` (located
in `settings/local.py`). `settings.local` usually imports and overrides settings
from settings.base, so you don't have to paste everything there, just the
values that have changed.

On windows there seem to be a few problems stopping the bot. Just press Ctrl+C
long enough and it will eventually terminate :)
