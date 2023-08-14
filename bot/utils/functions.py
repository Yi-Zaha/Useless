import asyncio
import base64
import logging
import multiprocessing
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial, wraps
from urllib.parse import urlparse

import cachetools
import cloudscraper
import pyrogram
import requests
from bs4 import BeautifulSoup
from html_telegraph_poster import TelegraphPoster
from pyrogram import types
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, MessageNotModified, RPCError, UserNotParticipant

from bot import LOGS, bot

# Data Caches
chat_photos = {}
invitation_links = {}
chat_messages = cachetools.TTLCache(maxsize=128, ttl=30 * 60)


# Utility Functions


def async_wrap(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=multiprocessing.cpu_count() * 5)
        try:
            result = await loop.run_in_executor(
                executor, partial(func, *args, **kwargs)
            )
            return result
        finally:
            await loop.run_in_executor(None, executor.shutdown, True)

    return wrapper


def b64_encode(string):
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    base64_string = base64_bytes.decode("ascii").rstrip("=")
    return base64_string


def b64_decode(base64_string):
    base64_string = base64_string.rstrip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    string_bytes = base64.urlsafe_b64decode(base64_bytes)
    string = string_bytes.decode("ascii")
    return string


def is_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def split_list(lst: list, index: int) -> list[list]:
    return [lst[i : i + index] for i in range(0, len(lst), index)]


# Network Functions


@async_wrap
def get_link(link: str, post: bool = False, cloud: bool = False, *args, **kwargs):
    session = cloudscraper.CloudScraper() if cloud else requests.Session()
    method = session.post if post else session.get
    response = method(link, *args, **kwargs)
    response.raise_for_status()
    return response


@async_wrap
def get_soup(
    url: str,
    parser: str = "html.parser",
    post: bool = False,
    cloud: bool = False,
    *args,
    **kwargs,
):
    session = cloudscraper.CloudScraper() if cloud else requests.Session()
    method = session.post if post else session.get
    response = method(url, *args, **kwargs)
    return BeautifulSoup(response.text, parser)


# Time and Numeric Functions


def is_numeric(inp: str):
    inp = inp.strip()
    try:
        int(inp)
        return True
    except ValueError:
        try:
            float(inp)
            return True
        except ValueError:
            pass
    return False


def humanbytes(size):
    if not size:
        return "0 B"
    units = ["", "K", "M", "G", "T"]
    for unit in units:
        if size < 1024:
            break
        size /= 1024
    return f"{size:.2f}{unit}B" if isinstance(size, float) else f"{size}{unit}B"


def readable_time(seconds: int) -> str:
    count = 0
    ping_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]

    while count < 4:
        count += 1
        if count < 3:
            remainder, result = divmod(seconds, 60)
        else:
            remainder, result = divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)

    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        ping_time += time_list.pop() + ", "

    time_list.reverse()
    ping_time += ":".join(time_list)

    return ping_time


# Chat and Message Functions


async def is_user_subscribed(user_id: int, chat_id: int):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except UserNotParticipant:
        pass
    except Exception as e:
        logging.getLogger(__name__).info(
            f"Error while checking user subscription status: {e}", exc_info=True
        )
        return None
    return False


async def get_chat_pic(chat_id: int, refresh: bool = None):
    if not refresh and chat_photos.get(chat_id):
        return chat_photos[chat_id]

    try:
        chat = await bot.get_chat(chat_id)
        if chat.photo:
            photo = await bot.download_media(chat.photo.big_file_id)
            chat_photos[chat_id] = photo
            return photo
    except BaseException:
        pass


async def get_chat_invite_link(chat_id: int, refresh: bool = None):
    if not refresh and invitation_links.get(chat_id):
        return invitation_links[chat_id]
    try:
        chat = await bot.get_chat(chat_id)
        link = f"https://t.me/{chat.username}" if chat.username else chat.invite_link
        invitation_links[chat_id] = link
        return link
    except BaseException:
        return None


async def get_chat_messages(chat, first_msg_id, last_msg_id, refresh=None):
    ids_range = list(range(first_msg_id, last_msg_id))
    _id = f"{chat}_{first_msg_id}-{last_msg_id}"
    if not refresh:
        if chat_messages.get(_id):
            return chat_messages[_id]
    messages = []
    for ids in split_list(ids_range, 200):
        messages += await bot.get_messages(chat, ids)
    chat_messages[_id] = messages
    return messages


async def get_chat_link_from_msg(message):
    if message.chat.username:
        return f"https://t.me/{message.chat.username}"
    elif message.chat.type.value == "private":
        return f"tg://user?id={message.chat.id}"
    else:
        chat_invite = await get_chat_invite_link(message.chat.id)
        return chat_invite if chat_invite else message.link.replace("-100", "")


# Telegraph Functions


@async_wrap
def post_to_telegraph(
    title: str, content: str, author: str = None, author_url: str = None
):
    if not author and not author_url:
        author = bot.me.first_name
        author_url = f"https://telegram.dog/{bot.me.username}"
    client = TelegraphPoster()
    client.create_api_token(author)
    try:
        page = client.post(title, author, text=content, author_url=author_url)
    except BaseException:
        return None
    return page["url"].replace("telegra.ph/", "graph.org/")


async def images_to_graph(title, image_urls: list, author=None, author_url=None):
    graph_link = await post_to_telegraph(
        title,
        "".join(f"<img src='{url}'/>" for url in image_urls),
        author=author,
        author_url=author_url,
    )
    return graph_link


# Other Utility Functions


def generate_share_url(mode, first_msg_id, last_msg_id):
    share_type = (
        "TimedBatchMsgs"
        if mode.lower() == "expiry"
        else "ProtectedBatchMsgs"
        if mode.lower() == "protect"
        else "BatchMsgs"
    )
    b64_code = b64_encode(f"{share_type}_{first_msg_id}-{last_msg_id}")
    return f"https://telegram.me/{bot.me.username}?start=cached-{b64_code}"


def retry_on_flood(function):
    async def wrapper(*args, **kwargs):
        while True:
            try:
                return await function(*args, **kwargs)
            except FloodWait as fw:
                fw.value += 1
                LOGS.info(
                    f"Floodwait, Waiting for {fw.value} seconds before continuing (required by {function.__qualname__})"
                )
                await asyncio.sleep(fw.value)
                continue
            except RPCError as err:
                if err.MESSAGE == "FloodWait":
                    err.value += 1
                    LOGS.info(
                        f"Floodwait, Waiting for {fw.value} seconds before continuing (required by {function.__qualname__})"
                    )
                    await asyncio.sleep(err.value)
                    continue
                raise
            except Exception:
                raise

    return wrapper


def _wrap(client):
    for name in dir(client):
        method = getattr(client, name)

        if name.startswith(("send_", "get_")):
            flood_wrap = retry_on_flood(method)
            setattr(client, name, flood_wrap)


_wrap(bot)
if bot.user:
    _wrap(bot.user)


async def restart_bot():
    pull_res = await run_cmd("git fetch -f && git pull -f")
    if "requirements.txt" in pull_res[0]:
        await run_cmd("pip install -U -r requirements.txt")
    os.execl(sys.executable, sys.executable, "-m", "bot")


bot.reboot = restart_bot


async def edit_and_delete(message, text=None, **kwargs):
    time = kwargs.pop("time", 8)
    try:
        await message.edit_text(text, **kwargs)
    except FloodWait as fw:
        await asyncio.sleep(fw.value)
        return await edit_and_delete(message, text, time=time, **kwargs)
    except MessageNotModified:
        pass

    await asyncio.sleep(int(time))
    await message.delete()


async def ask_msg(
    msg: types.Message,
    text: str,
    quote: bool = False,
    filters: pyrogram.filters = pyrogram.filters.text,
    timeout: int = 90,
):
    request = await msg.reply(text, quote=quote)

    try:
        response = await msg._client.listen.Message(
            filters, id=pyrogram.filters.chat(msg.chat.id), timeout=timeout
        )
    except asyncio.TimeoutError:
        await request.edit("Process Timed Out. You were late in responding.")
        raise

    if response.text and response.text.lower().split()[0] in ["/cancel"]:
        await request.edit("Cancelled!")
        raise asyncio.CancelledError
    
    return request, response


async def run_cmd(cmd: str) -> tuple[str, str]:
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode().strip(), stderr.decode().strip()


async def retry_func(func, tries=5):
    while tries:
        tries -= 1
        try:
            result = await func
        except BaseException:
            continue
        if result[-1]:
            break
