import time

import uvloop
uvloop.install()

from pyrogram import Client
from pyromod import listen

from .config import Config
from .logger import LOGGER


bot = Client(
    "Useless-Bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    plugins=dict(root="bot.plugins"),
    ipv6=Config.USE_IPV6,
    max_concurrent_transmissions=3,
)
uB = None
if Config.UB and Config.UB_SESSION:
    uB = Client(
        "Useless-User",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        session_string=Config.SESSION_STRING,
        ipv6=Config.USE_IPV6,
        max_concurrent_transmissions=3,
    )


bot.user = uB
LOGS = LOGGER("UselessBot")
StartTime = time.time()
LOG_CHAT = Config.get("LOG_CHAT", -1001568226560)
CACHE_CHAT = Config.get("CACHE_CHAT", -1001821705224)
OWNER_ID = Config.get("OWNER_ID", 5905126281)
SUDOS = Config.get("SUDOS", "5370531116 5551387300  5905126281").split()
SUDOS = list(map(int, SUDOS)) + [OWNER_ID]
ALLOWED_USERS = SUDOS + [5591954930]
