import asyncio
from pathlib import Path

from pyrogram import idle

from bot import LOG_CHAT, LOGS, bot
from bot.utils import ascheduler
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.db import dB


def start_clients():
    LOGS.info("Initializing clients...")
    bot.start()
    if bot.user:
        bot.user.start()

    bot.send_message(LOG_CHAT, "BOT IS ONLINE!")
    if bot.user:
        bot.user.send_message(LOG_CHAT, "USERBOT IS ONLINE!")


def stop_clients():
    LOGS.info("Stopping clients...")
    bot.send_message(LOG_CHAT, "BOT IS GOING OFFLINE.")
    bot.stop()
    if bot.user:
        bot.user.send_message(LOG_CHAT, "USERBOT IS GOING OFFLINE.")
        bot.user.stop()


async def main():
    Path("cache").mkdir(exist_ok=True)

    if thumb_url := await dB.get_key("THUMBNAIL"):
        await AioHttp.download(thumb_url, filename="thumb.jpg")

    if ascheduler.get_jobs():
        LOGS.info("Async Scheduler started.")
        ascheduler.start()

    await idle()


if __name__ == "__main__":
    loop = asyncio.get_event_loop_policy().get_event_loop()
    start_clients()
    try:
        loop.run_until_complete(main())
    except BaseException:
        stop_clients()
        loop.close()
        raise
