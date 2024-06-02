import os
from logging import (
    INFO,
    WARNING,
    Logger,
    StreamHandler,
    basicConfig,
    getLogger,
    handlers,
)


def LOGGER(name: str) -> Logger:
    return getLogger(name)


LOG_FILE = "logs.txt"
if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)
basicConfig(
    format="%(asctime)s || %(name)s || %(levelname)s ›› %(message)s",
    level=INFO,
    handlers=[
        handlers.RotatingFileHandler(LOG_FILE, maxBytes=200000, backupCount=3),
        StreamHandler(),
    ],
)
warning_modules = [
    "aiohttp.access",
    "apscheduler",
    "pyrogram.session",
    "pyrogram.connection",
    "pyrogram.parser",
]
for name in warning_modules:
    LOGGER(name).setLevel(WARNING)
