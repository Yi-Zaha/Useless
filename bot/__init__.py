import time

import uvloop
uvloop.install()

from convopyro import Conversation
from pyrogram import Client

from .config import Config
from .logger import LOGGER


bot = Client(
    "Useless-Bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    plugins=dict(root="bot.plugins"),
    ipv6=bool(Config.USE_IPV6),
    max_concurrent_transmissions=3,
    workers=32,
)
Conversation(bot)

uB = None
if Config.UB and Config.UB_SESSION:
    uB = Client(
        "Useless-User",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        session_string=Config.UB_SESSION,
        no_updates=bool(Config.NO_UB_UPDATES),
        ipv6=bool(Config.USE_IPV6),
        max_concurrent_transmissions=3,
        workers=32,
    )
    Conversation(uB)


bot.ub = uB
LOGS = LOGGER("UselessBot")
StartTime = time.time()
LOG_CHAT = Config.get("LOG_CHAT", -1001568226560)
CACHE_CHAT = Config.get("CACHE_CHAT", -1001821705224)
PHUB_CHANNEL = Config.get("PORNHWA_HUB", -1001800092422)
OWNER_ID = Config.get("OWNER_ID", 5905126281)
SUDOS = Config.get("SUDOS", "5370531116 5551387300  5905126281 6768114074").split()
SUDOS = list(map(int, SUDOS)) + [OWNER_ID]
ALLOWED_USERS = SUDOS + [5591954930]
