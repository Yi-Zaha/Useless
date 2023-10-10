import asyncio
from contextlib import suppress
from pathlib import Path

from pyrogram import idle

from bot import LOG_CHAT, LOGS, bot
from bot.utils import ascheduler
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.db import dB


async def start_clients():
    LOGS.info("Initializing clients...")
    await bot.start()
    if bot.ub:
        await bot.ub.start()

    await bot.send_message(LOG_CHAT, "BOT IS ONLINE!")
    if bot.ub:
        try:
            await bot.ub.send_message(LOG_CHAT, "USERBOT IS ONLINE!")
        except:
            await bot.send_message(LOG_CHAT, "USERBOT IS ONLINE!")


async def stop_clients(stop=True):
    LOGS.info("Stopping clients...")
    await bot.send_message(LOG_CHAT, "BOT IS GOING OFFLINE.")
    with suppress(Exception):
        await bot.stop()
    if bot.ub:
        try:
            await bot.ub.send_message(LOG_CHAT, "USERBOT IS GOING OFFLINE.")
        except:
            await bot.send_message(LOG_CHAT, "USERBOT IS GOING OFFLINE.")
        with suppress(Exception):
            await bot.ub.stop()


async def main():
    Path("cache").mkdir(exist_ok=True)

    if thumb_url := await dB.get_key("THUMBNAIL"):
        await AioHttp.download(
            thumb_url.replace("telegra.ph", "graph.org"), filename="thumb.jpg"
        )

    if ascheduler.get_jobs():
        LOGS.info("Async Scheduler started.")
        ascheduler.start()

    await idle()


async def run_main():
    try:
        await start_clients()
        await main()
    except Exception as e:
        LOGS.error(str(e))
    finally:
        await stop_clients()


if __name__ == "__main__":
    loop = asyncio.get_event_loop_policy().get_event_loop()
    loop.run_until_complete(run_main())
