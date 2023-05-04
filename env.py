import os

DISCORD_TOKEN = None
WIT_TOKEN = None

def init_env():
    global DISCORD_TOKEN, WIT_TOKEN
    DISCORD_TOKEN = os.environ['SOUPBOT_DISCORD_TOKEN']
    WIT_TOKEN = os.environ['SOUPBOT_WIT_TOKEN']
