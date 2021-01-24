import _ctypes
import asyncio
import ctypes
import logging
import platform
from ctypes import CDLL

import discord
from discord.ext import commands

import settings

logger = logging.getLogger('discord.' + __name__)


def unload_dll(dll):
    if platform.system() == 'Windows':
        _ctypes.FreeLibrary(dll._handle)
    else:
        _ctypes.dlclose(dll._handle)


class SQFVMWrapper:
    def __init__(self, path):
        self.sqfvm_path = path
        self.libsqfvm = None
        self.lock = asyncio.Lock()

    def ready(self):
        return self.libsqfvm is not None

    def unload(self):
        if self.libsqfvm:
            unload_dll(self.libsqfvm)
            self.libsqfvm = None

    def load(self):
        if self.libsqfvm:
            self.unload()

        libsqfvm = CDLL(self.sqfvm_path)

        # void* sqfvm_create_instance(void* user_data, sqfvm_log_callback callback, float max_runtime_seconds)
        libsqfvm.sqfvm_create_instance.restype = ctypes.c_void_p
        libsqfvm.sqfvm_create_instance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float]

        # void sqfvm_destroy_instance(void* instance)
        libsqfvm.sqfvm_destroy_instance.restype = None
        libsqfvm.sqfvm_destroy_instance.argtypes = [ctypes.c_void_p]

        # int32_t sqfvm_load_config(void* instance, const char* contents, uint32_t length)
        libsqfvm.sqfvm_load_config.restype = ctypes.c_int32
        libsqfvm.sqfvm_load_config.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]

        # int32_t sqfvm_call(void* instance, void* call_data, char type, const char* code, uint32_t length)
        libsqfvm.sqfvm_call.restype = ctypes.c_int32
        libsqfvm.sqfvm_call.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char, ctypes.c_char_p,
                                        ctypes.c_uint32]

        # int32_t sqfvm_status(void* instance)
        libsqfvm.sqfvm_status.restype = ctypes.c_int32
        libsqfvm.sqfvm_status.argtypes = [ctypes.c_void_p]

        self.libsqfvm = libsqfvm

    # ==== Wrappers ===========================================================

    def _sqfvm_create_instance(self, user_data, callback, max_runtime_seconds):
        return self.libsqfvm.sqfvm_create_instance(user_data, callback, max_runtime_seconds)

    def _sqfvm_destroy_instance(self, instance):
        return self.libsqfvm.sqfvm_destroy_instance(instance)

    def _sqfvm_load_config(self, instance, contents, length):
        return self.libsqfvm.sqfvm_load_config(instance, contents, length)

    def _sqfvm_call(self, instance, call_data, type, code, length):
        return self.libsqfvm.sqfvm_call(instance, call_data, type, code, length)

    def _sqfvm_status(self, instance):
        return self.libsqfvm.sqfvm_status(instance)

    # ==== / Wrappers =========================================================

    sqfvm_error_codes = {
        0: 'calling the SQF-VM instance was successful',
        -1: 'the instance was null',
        -2: 'preprocessing failed',
        -3: 'parsing failed',
        -4: 'the instance is already running',
        -5: 'the provided type was invalid',
        -6: 'the execution did not succeed',
    }

    sqfvm_user_caused_error_codes = {-2, -3, -6}

    def get_error_message(self, code):
        internal = 'SQF-VM encountered an internal error'
        user_related = 'SQF-VM encountered an error while executing the code'

        if code in self.sqfvm_user_caused_error_codes:
            error_type = user_related
        else:
            error_type = internal

        try:
            message = '{}: {}'.format(error_type, self.sqfvm_error_codes[code])
        except KeyError:
            message = 'Unknown error! Error code: {}'.format(code)

        return message

    def call_sqf(self, code: str, timeout=10):
        data_out = []

        # FIXME: Find an easy way for this to simply be a method class instead of using a closure
        # typedef void(*sqfvm_log_callback)(void* user_data, void* call_data, int32_t severity, const char* message,
        #                                   uint32_t length);
        @ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_char_p, ctypes.c_uint32)
        def callback(user_data, call_data, severity, message, length):
            data_out.append(message.decode('utf8'))

        if not self.ready():
            return 'Error: SQF-VM not loaded correctly'

        code_bytes = code.encode('utf-8')

        instance = self._sqfvm_create_instance(None, callback, max_runtime_seconds=timeout)
        if not instance:
            return 'Error: SQF-VM could not create an instance'

        retval = self._sqfvm_call(instance, None, ord('s'), code_bytes, len(code_bytes))

        self._sqfvm_destroy_instance(instance)

        if retval != 0:
            return '\n'.join(data_out) + '\nError: ' + self.get_error_message(retval)

        return '\n'.join(data_out)

    async def call_sqf_async(self, code: str, timeout=10):
        async with self.lock:
            return await asyncio.get_event_loop().run_in_executor(None, self.call_sqf, code, timeout)


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

    def escape_markdown(self, text):
        prefix = '```sqf\n'
        suffix = '```'
        ellipsis = '(...)'

        if text == '':
            return '```\n```'  # Otherwise, Discord treats "sqf" as the message contents

        retval = '{}{}{}'.format(prefix, text, suffix)
        if len(retval) > 2000:
            text = text[:2000 - len(ellipsis)] + ellipsis  # "longtexthere" -> "longte(...)"
            retval = '{}{}{}'.format(prefix, text, suffix)

        return retval

    def strip_mentions_and_markdown(self, message, strip_command_marker=False):
        content = message.content.strip()

        if strip_command_marker and content.startswith('!sqf'):
            content = content[5:]

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
        code_to_execute = self.strip_mentions_and_markdown(ctx.message, strip_command_marker=True)

        async with ctx.typing():
            sqf_result = await self.execute_sqf(code_to_execute)
        await ctx.channel.send(self.escape_markdown(sqf_result))

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

        if self.bot.user.id in message.raw_mentions:
            code_to_execute = self.strip_mentions_and_markdown(message)

        elif type(message.channel) is discord.DMChannel:  # Always interpret when DM
            code_to_execute = self.strip_mentions_and_markdown(message)

        elif message.channel.name.startswith('sqf') and message.content.startswith('```sqf'):
            code_to_execute = self.strip_mentions_and_markdown(message)

        if code_to_execute:
            async with message.channel.typing():
                sqf_result = await self.execute_sqf(code_to_execute)
            await message.channel.send(self.escape_markdown(sqf_result))


def setup(bot):
    bot.add_cog(Interpreter(bot))
