import asyncio
import base64
import inspect
import logging
import multiprocessing
import os
import random
import string
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from functools import partial, wraps
from typing import Union
from urllib.parse import urljoin, urlparse

import cachetools
import cloudscraper
import pyrogram
import requests
from bs4 import BeautifulSoup
from html_telegraph_poster import html_to_telegraph
from html_telegraph_poster.html_to_telegraph import TelegraphPoster
from pyrogram import raw, types
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, MessageNotModified, RPCError, UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from telegraph.aio import Telegraph
from Levenshtein import hamming

from bot import LOGS, bot

# Data Caches
chat_photos = {}
invitation_links = {}
chat_messages = cachetools.TTLCache(maxsize=1024 * 1024, ttl=30 * 60)


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
    return base64_bytes.decode("ascii").rstrip("=")


def b64_decode(base64_string):
    base64_string = base64_string.rstrip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    string_bytes = base64.urlsafe_b64decode(base64_bytes)
    return string_bytes.decode("ascii")


def get_random_id(limit=9):
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choices(alphabet, k=limit))


def is_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def split_list(lst: list, index: int) -> list[list]:
    return [lst[i : i + index] for i in range(0, len(lst), index)]


@async_wrap
def remove_files(files):
    with suppress(BaseException):
        os.remove(files)
    with suppress(BaseException):
        for file in files:
            with suppress(BaseException):
                os.remove(file)


def string_similarity(string1, string2):
    distance = hamming(string1.lower(), string2.lower())
    net_length = len(string1+string2)
    return 100 - (distance * 100 / net_length)


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
        with suppress(ValueError):
            float(inp)
            return True
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
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)

    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        ping_time += f"{time_list.pop()}, "

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


async def get_chat_link(message=None, chat=None):
    if chat := chat or (message and message.chat):
        chat_invite = await get_chat_invite_link(chat)
        if chat_invite:
            return chat_invite

        if message:
            return message.link.replace("-100", "")

    return None


async def get_chat_pic(chat_id: int, refresh: bool = None):
    if not refresh and chat_id in chat_photos:
        return chat_photos[chat_id]

    try:
        chat = await bot.get_chat(chat_id)
        if chat.photo:
            photo = await bot.download_media(chat.photo.big_file_id)
            chat_photos[chat_id] = photo
            return photo
    except Exception as e:
        print(f"Error in get_chat_pic: {e}")


async def get_chat_invite_link(chat, refresh: bool = None):
    chat_id = chat.id if isinstance(chat, types.Chat) else chat

    if not refresh and chat_id in invitation_links:
        return invitation_links[chat_id]

    try:
        chat = chat if isinstance(chat, types.Chat) else await bot.get_chat(chat_id)
        if chat.username:
            link = f"https://t.me/{chat.username}"
        elif chat.invite_link:
            link = chat.invite_link
        elif chat.type == enums.ChatType.PRIVATE:
            link = f"tg://user?id={chat.id}"
        invitation_links[chat_id] = link
        return link
    except Exception as e:
        print(f"Error in get_chat_invite_link: {e}")

    return None


async def get_chat_messages(
    chat, first_msg_id, last_msg_id, client=bot, refresh=None, sleep_for_flood=0
):
    ids_range = list(range(first_msg_id, last_msg_id))
    messages = []
    cache_messages = chat_messages.setdefault(chat, {})
    for message_ids in split_list(ids_range, 200):
        uncached_ids = [
            message_id for message_id in message_ids if message_id not in cache_messages
        ]
        if uncached_ids:
            msgs = await client.get_messages(chat, uncached_ids)
            for msg in msgs:
                cache_messages[msg.id] = msg
        messages.extend([cache_messages[message_id] for message_id in message_ids])
        await asyncio.sleep(sleep_for_flood)
    return messages


async def get_latest_chat_msg(channel):
    return (
        await bot.invoke(
            raw.functions.updates.GetChannelDifference(
                channel=await bot.resolve_peer(channel),
                filter=raw.types.ChannelMessagesFilterEmpty(),
                pts=1,
                limit=1,
            )
        )
    ).dialog.top_message


# Telegraph Functions


html_to_telegraph.api_url = "https://api.graph.org"
html_to_telegraph.base_url = "https://graph.org"


@async_wrap
def post_to_telegraph(
    title: str, content: str, author: str = None, author_url: str = None
):
    if not author and not author_url:
        author = bot.me.first_name
        author_url = f"https://telegram.dog/{bot.me.username}"
    client = TelegraphPoster(use_api=True, telegraph_api_url="https://api.graph.org")
    client.create_api_token(author)
    try:
        page = client.post(title, author, text=content, author_url=author_url)
    except Exception as e:
        print(e)
        return
    return page["url"].replace("telegra.ph", "graph.org")


async def file_to_graph(f):
    client = Telegraph(domain="graph.org")
    urls = [
        urljoin("https://graph.org", item["src"])
        for item in await client.upload_file(f)
    ]
    return urls if len(urls) > 1 else urls[0]


async def images_to_graph(title, image_urls: list, author=None, author_url=None):
    html_content = "".join(f'<img src="{url}"/>\n' for url in image_urls)
    return await post_to_telegraph(
        title,
        html_content,
        author=author,
        author_url=author_url,
    )


# Other Utility Functions


def generate_share_url(mode, first_msg_id, last_msg_id, bot_username=None):
    share_type = (
        "202"
        if mode.lower() == "expiry"
        else "201" if mode.lower() == "protect" else "200"
    )
    b64_code = b64_encode(f"{share_type}-{first_msg_id}-{last_msg_id}")
    return (
        f"https://telegram.me/{bot_username or bot.me.username}?start=cached-{b64_code}"
    )


def retry_on_flood(function):
    async def wrapper(*args, **kwargs):
        for _ in range(2):
            try:
                result = function(*args, **kwargs)
                if inspect.iscoroutine(result):
                    return await result
                return result
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

        if inspect.isasyncgenfunction(method) or inspect.isgeneratorfunction(method):
            continue

        if name.startswith(("send_", "get_")) and callable(method):
            flood_wrap = retry_on_flood(method)
            setattr(client, name, flood_wrap)


_wrap(bot)
if bot.ub:
    _wrap(bot.ub)


async def restart_bot():
    pull_res = await run_cmd("git checkout . && git pull -f")
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


async def ask_message(
    message_or_chat: Union[int, types.Message],
    text: str,
    filters: pyrogram.filters = pyrogram.filters.text,
    from_user: int = None,
    edit: bool = False,
    pin_edit: bool = False,
    timeout: int = 300,
    **kwargs,
):
    if isinstance(message_or_chat, types.Message):
        if edit:
            request = await message_or_chat.edit(text, **kwargs)
            if pin_edit:
                with suppress(Exception):
                    await (await request.pin(both_sides=True)).delete()
        else:
            request = await message_or_chat.reply(text, **kwargs)
        chat_id = message_or_chat.chat.id

    elif isinstance(message_or_chat, int):
        request = await bot.send_message(message_or_chat, text, **kwargs)
        chat_id = message_or_chat

    try:
        response = await bot.listen.Message(
            filters,
            id=(
                pyrogram.filters.chat(chat_id)
                if not from_user
                else str(chat_id * from_user)
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        await request.reply(
            f"<b>Process Timed Out: You were too late in responding.</b>"
        )
        raise
    finally:
        if pin_edit:
            with suppress(Exception):
                await request.unpin()

    if response.text and response.text.lower().split()[0] in ["/cancel"]:
        await request.reply("Okay, cancelled the process!")
        raise asyncio.CancelledError

    return request, response


async def ask_callback_options(
    message_or_chat: Union[int, types.Message],
    text: str,
    options: list,
    user_id: int = None,
    edit: bool = False,
    pin_edit: bool = False,
    split: int = 3,
    timeout: int = 300,
    **kwargs,
):
    rand_id = get_random_id(8)
    query = rf"ask_cb{rand_id}{user_id or ''}"
    buttons = [
        (
            InlineKeyboardButton(option[0], f"{query}:{option[1]}")
            if isinstance(option, (list, tuple))
            else InlineKeyboardButton(option, f"{query}:{option}")
        )
        for option in options
    ]

    buttons = split_list(buttons, split) if split else split_list(buttons, 1)
    if "reply_markup" in kwargs:
        del kwargs["reply_markup"]

    if isinstance(message_or_chat, types.Message):
        if edit:
            request = await message_or_chat.edit_text(
                text, reply_markup=InlineKeyboardMarkup(buttons), **kwargs
            )
            if pin_edit:
                with suppress(Exception):
                    await (await request.pin(both_sides=True)).delete()
        else:
            request = await message_or_chat.reply_text(
                text, reply_markup=InlineKeyboardMarkup(buttons), **kwargs
            )
    elif isinstance(message_or_chat, int):
        kwargs.pop("quote", None)
        request = await bot.send_message(
            message_or_chat, text, reply_markup=InlineKeyboardMarkup(buttons), **kwargs
        )
    else:
        raise ValueError(type(message_or_chat).__name__)

    while True:
        try:
            callback = await bot.listen.CallbackQuery(
                pyrogram.filters.regex(query), timeout=timeout
            )
        except asyncio.TimeoutError:
            await request.edit(
                f"{request.text.html}\n<b>Process Timed Out: You were late in responding.</b>"
            )
            if pin_edit:
                with suppress(Exception):
                    await request.unpin()
            raise

        if not user_id or user_id == callback.from_user.id:
            break

        with suppress(Exception):
            await callback.answer(
                "This button can only be used by the one who issued the command.",
                show_alert=True,
            )
    if pin_edit:
        with suppress(Exception):
            await request.unpin()
    selection = callback.data.split(":", 1)[1]
    with suppress(Exception):
        await callback.answer(f"Okay! Selected option - {selection}", show_alert=True)

    return request, selection


async def run_cmd(cmd: str) -> tuple[str, str]:
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode().strip(), stderr.decode().strip()


async def retry_func(func, *args, tries=5, no_output=False, **kwargs):
    while tries:
        tries -= 1
        try:
            output = await func(*args, **kwargs)
        except BaseException:
            if tries > 1:
                continue
            raise
        if no_output:
            break
        if _is_iterable(output):
            if all(output):
                return output
        elif bool(output):
            return output


def _is_iterable(obj):
    try:
        iter(obj)
        return True
    except TypeError:
        return False


def get_function_args(func):
    sig = inspect.signature(func)
    args = [
        param.name
        for param in sig.parameters.values()
        if param.default == inspect.Parameter.empty
    ]
    kwargs = [
        param.name
        for param in sig.parameters.values()
        if param.default != inspect.Parameter.empty
    ]
    return args, kwargs
