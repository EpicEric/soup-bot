import os

DISCORD_TOKEN = None
WIT_TOKEN = None
CUSTOM = {}

def init_env():
    global DISCORD_TOKEN, WIT_TOKEN, CUSTOM
    DISCORD_TOKEN = os.environ['SOUPBOT_DISCORD_TOKEN']
    WIT_TOKEN = os.environ['SOUPBOT_WIT_TOKEN']
    for envvar in os.environ:
        if envvar.startswith('SOUPBOT_CUSTOM_'):
            CUSTOM["$" + envvar[len('SOUPBOT_CUSTOM_'):].lower()] = os.environ[envvar]

