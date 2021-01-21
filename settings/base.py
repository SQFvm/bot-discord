################################################################################
# Bots settings
################################################################################

import os

# Copy this whole structure and replace with your values, in local.py
SQF_BOT = {
    'bot_token': '<Set this value to your bot token in local.py>',
    'name': 'SQFBot base',
}

ADMINS = [
    105784568346324992,  # X39
]

VMPATH = os.path.join('..', 'SQFvm')
BUILD_ENV = {}  # {'CC': 'gcc-8', 'CXX':'g++-8'}