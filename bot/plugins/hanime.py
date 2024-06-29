import asyncio
import json
import os
import random
import re
import secrets
import textwrap
from typing import Union

import cachetools
from bs4 import BeautifulSoup
from dateutil import parser
from pyrogram import Client, filters
from pyrogram.types import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from yt_dlp import YoutubeDL

from bot import ALLOWED_USERS
from bot.plugins.filetools import send_media
from bot.utils import non_command_filter, user_agents
from bot.utils.aiohttp_helper import AioHttp, AioHttpHelper
from bot.utils.functions import (
    ask_message,
    async_wrap,
    get_random_id,
    post_to_telegraph,
    retry_func,
    run_cmd,
)
from bot.utils.singleton import Singleton

cache = {}
timed_cache = cachetools.TTLCache(ttl=60 * 60, maxsize=1024 * 1024)


class OppaiStream(AioHttpHelper, metaclass=Singleton):
    BASE_URL = "https://oppai.stream"

    def __init__(self, *args, **kwargs):
        if "headers" not in kwargs:
            kwargs["headers"] = {"User-Agent": random.choice(user_agents)}
        super().__init__(1, *args, **kwargs)
        self.headers = kwargs["headers"]

    async def latest(self, page=1, limit=24):
        return await self.search(order="uploaded", page=page, limit=limit)

    async def popular(self, page=1, limit=24):
        return await self.search(order="views", page=page, limit=limit)

    async def search(
        self,
        query="",
        order="recent",
        page=1,
        limit=24,
        genres="",
        blacklist="",
        studio="",
        group_results=None,
    ):
        url = f"{self.BASE_URL}/actions/search.php"
        params = {
            "text": query,
            "order": order,
            "page": page,
            "limit": limit,
            "genres": genres,
            "blacklist": blacklist,
            "studio": studio,
        }

        content = await self.request(url, params=params)
        soup = BeautifulSoup(content, "html.parser")
        divs = soup.find_all("div", "episode-shown")

        results = [self._episode_data_from_div(div) for div in divs]

        if group_results:
            new_results = {}
            for result in results:
                show_name = result["name"]

                if show_name not in new_results:
                    new_results[show_name] = []

                del result["name"]
                new_results[show_name].append(result)

            for show in new_results:
                new_results[show].sort(key=lambda e: e["episode"])

            return new_results

        return results

    async def get_episode(self, url):
        content = await self.request(url)
        soup = BeautifulSoup(content, "html.parser")
        episode_info = soup.find("div", "episode-info")
        name, episode = episode_info.find("h1").text.split(" Ep ")
        description = episode_info.find("div", "description").text.strip()
        tags = [
            a.text.strip()
            for a in episode_info.find("div", "tags").find_all("a", "tag")
        ]
        studios = [a.text.strip() for a in episode_info.find_all("a", "red")]
        preview_imgs = [
            img["src"]
            for img in episode_info.find("div", "preview-grid").find_all("img")
        ]

        video = soup.find("video", id="episode")
        poster_url = video["poster"]
        subtitles = {track["label"]: track["src"] for track in video.find_all("track")}

        resolution_links = json.loads(
            re.search(rb"var availableres.*=(.*);", content).group(1)
        )

        similar_eps = [
            self._episode_data_from_div(div)
            for div in soup.find_all("div", "episode-shown")
        ]

        return {
            "episode": episode,
            "show_name": name,
            "description": description,
            "tags": tags,
            "studios": studios,
            "screenshots": preview_imgs,
            "poster": poster_url,
            "subtitles": subtitles,
            "streams": resolution_links,
            "all_episodes": similar_eps,
        }

    def _episode_data_from_div(self, div):
        a = div.find("div").find("a")
        hentai_url = a["href"]
        div.find("img", "cover-img-in")["src"]
        return {
            "name": div["name"],
            "episode": div["ep"],
            "url": hentai_url,
            "id": div["id"],
            "show_id": div["idgt"],
            "description": div["desc"],
            "tags": div["tags"].split(","),
            "studios": [
                a.text.strip() for a in a.find("div", "wrap-ep-info").find_all("a")
            ],
        }


class HanimeTV:
    SEARCH_URL = "https://search.htv-services.com"
    HANIME_API_URL = "https://hanime.tv/api/v8"
    HANIME_API_TOKEN = "-69XyedgVe6jO7w2kAb1IdG9W3psBrOKhYmkUggeeEjOjK8j67ehRu3nhB2_yGWWBAnfhLJyxCy_cDnIU0IlJF6FBVpJmJdfzDwPin3B-ztxlAoOH34YWLLCbO0-RWjO(-(0)-)Rz1soD-a-OL2BalbTbOdcA=="

    @staticmethod
    async def search(
        query: str,
        page: int = 0,
        tags: str = None,
        brands: str = None,
        blacklist: str = None,
        order_by: str = None,
        ordering: str = None,
    ):
        headers = {"Content-Type": "application/json; charset=utf-8"}

        search_data = {
            "search_text": query,
            "tags": tags.split(",") if tags else [],
            "brands": brands.split(",") if brands else [],
            "blacklist": blacklist.split(",") if blacklist else [],
            "order_by": order_by.split(",") if order_by else [],
            "ordering": ordering.split(",") if ordering else [],
            "page": page,
        }

        response_data = await AioHttp.request(
            HanimeTV.SEARCH_URL, "POST", headers=headers, json=search_data, re_json=True
        )

        return {
            "response": json.loads(response_data["hits"]),
            "page": response_data["page"],
            "total_pages": response_data["nbPages"],
        }

    @staticmethod
    async def recent(page: int = 0):
        headers = {"Content-Type": "application/json; charset=utf-8"}

        search_data = {
            "search_text": "",
            "tags": [],
            "brands": [],
            "blacklist": [],
            "order_by": "created_at_unix",
            "ordering": "desc",
            "page": page,
        }

        response_data = await AioHttp.request(
            HanimeTV.SEARCH_URL, "POST", headers=headers, json=search_data, re_json=True
        )

        return {
            "response": json.loads(response_data["hits"]),
            "page": response_data["page"],
            "total_pages": response_data["nbPages"],
        }

    @staticmethod
    async def trending(time: str = "month", page: int = 0):
        headers = {"X-Signature-Version": "web2", "X-Signature": secrets.token_hex(32)}

        return await AioHttp.request(
            f"{HanimeTV.HANIME_API_URL}/browse-trending?time={time}&page={page}",
            headers=headers,
            re_json=True,
        )

    @staticmethod
    async def details(id: Union[int, str]):
        headers = {
            "X-Signature-Version": "web2",
            "X-Signature": secrets.token_hex(32),
            "User-Agent": random.choice(user_agents),
        }
        try:
            return await AioHttp.request(
                f"https://hdome.koyeb.app/get_video_data/{id}?api_key=YATO.HENTI.GOD",
                headers=headers,
                re_json=True,
            )
        except BaseException:
            response_data = await AioHttp.request(
                f"https://hdome-api-2k22.onrender.com/hanimetv/get_details?video_id={id}&api_key=YATO.HENTI.GOD",
                re_json=True,
            )
            return {"hanimetv": response_data}

        created_at = parser.parse(response_data["hentai_video"]["created_at"]).strftime(
            "%Y %m %d"
        )
        released_date = parser.parse(
            response_data["hentai_video"]["released_at"]
        ).strftime("%Y %m %d")
        views = "{:,}".format(response_data["hentai_video"]["views"])
        tags = [
            tag["text"].title() for tag in response_data["hentai_video"]["hentai_tags"]
        ]
        streams = response_data["videos_manifest"]["servers"][0]["streams"]

        return {
            "id": response_data["hentai_video"]["id"],
            "query": response_data["hentai_video"]["slug"],
            "name": response_data["hentai_video"]["name"],
            "description": response_data["hentai_video"]["description"],
            "brand": response_data["hentai_video"]["brand"],
            "franchise": response_data["hentai_franchise"],
            "franchise_videos": response_data["hentai_franchise_hentai_videos"],
            "cover_url": response_data["hentai_video"]["cover_url"],
            "poster_url": response_data["hentai_video"]["poster_url"],
            "screenshots": response_data["hentai_video_storyboards"][0]["url"],
            "views": views,
            "streams": streams,
            "created_at": created_at,
            "released_date": released_date,
            "is_censored": response_data["hentai_video"]["is_censored"],
            "tags": tags,
            "next": response_data["next_hentai_video"],
            "next_random": response_data["next_random_hentai_video"],
        }

    @staticmethod
    async def link(id: Union[int, str]):
        headers = {"X-Session-Token": HanimeTV.HANIME_API_TOKEN}
        response_data = await AioHttp.request(
            f"{HanimeTV.HANIME_API_URL}/video?id={id}", headers=headers, re_json=True
        )

        return response_data["videos_manifest"]["servers"][0]["streams"]


@Client.on_message(filters.command("hentai") & filters.user(ALLOWED_USERS))
async def search_handler(client, message):
    if len(message.command) == 1:
        status = await message.reply(
            "Tell me the query you want to search for.", reply_markup=ForceReply()
        )
        try:
            query_message = await client.listen.Message(
                filters.user(message.from_user.id) & filters.text & non_command_filter,
                timeout=60,
            )
        except asyncio.TimeoutError:
            return await status.edit(
                "The command has been cancelled since you were late in responding."
            )
        query = query_message.text.strip()
        status = await query_message.reply("Searching...", quote=True)
    else:
        query = " ".join(message.command[1:])
        status = await message.reply("Searching...", quote=True)

    query_id = get_random_id()
    cache[query_id] = query
    await search_query(
        client, status, query_id=query_id, page=0, button_user=message.from_user.id
    )


@Client.on_callback_query(filters.regex(r"^hanime_s:.*"))
async def search_query(
    client, update, query_id=None, page=0, button_user=None, cb=False
):
    if not query_id:
        cb = True
        query_id, page = update.data.split(":")[1:3]
        page, button_user = int(page), update.from_user.id
        if str(button_user) not in update.data:
            return await update.answer(
                "This button can only be used by the one who issued the command.",
                show_alert=True,
            )

    if query_id not in cache:
        if getattr(update.message.reply_to_message, "text", None):
            query = (
                update.message.reply_to_message.text.split(" ", maxsplit=1)[1]
                if update.message.reply_to_message.text.lower().startswith("/hentai")
                else update.message.reply_to_message.text
            )
            cache[query_id] = query
        else:
            await update.answer(
                "Sorry, the bot restarted! Please redo the command.", show_alert=True
            )
            return

    try:
        result = await HanimeTV.search(cache[query_id])
        response = result["response"]
    except Exception:
        text = "Sorry, there was an error parsing response from the API. Please try again later!"
        if cb:
            await update.answer(text, show_alert=True)
        else:
            await update.edit(text)
        return

    if not response:
        text = (
            "No results found for the given query."
            if page < 1
            else "No further results are available!"
        )
        if cb:
            await update.answer(text, show_alert=True)
        else:
            await update.edit(text)
        return

    buttons = [
        [
            InlineKeyboardButton(
                data["name"], f'hanime_i:{data["id"]}:{query_id}:{button_user}'
            )
        ]
        for data in response
    ]

    prev_button = InlineKeyboardButton(
        "⟨ Previous Page", f"hanime_s:{query_id}:{page - 1}:{button_user}"
    )
    next_button = InlineKeyboardButton(
        "Next Page ⟩", f"hanime_s:{query_id}:{page + 1}:{button_user}"
    )

    result["total_pages"] -= 1
    if page < result["total_pages"]:
        buttons.append([prev_button, next_button] if page > 0 else [next_button])
    elif page == result["total_pages"] and page > 0:
        buttons.append([prev_button])

    if cb:
        await update.answer()
        await update.edit_message_text(
            f"Search results for <code>{cache[query_id]}</code>.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    else:
        await update.edit_text(
            f"Search results for <code>{cache[query_id]}</code>.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


@Client.on_callback_query(filters.regex(r"^hanime_i:.*"))
async def hanime_query(client, callback):
    hanime_id, query_id = callback.data.split(":")[1:3]
    if str(callback.from_user.id) not in callback.data:
        return await callback.answer(
            "This button can only be used by the one who issued the command.",
            show_alert=True,
        )

    try:
        result = await HanimeTV.details(hanime_id)
        result = result["hanimetv"]
        name = result["name"]
    except Exception:
        await callback.answer(
            "Sorry, there was an error parsing response from the API. Please try again later!",
            show_alert=True,
        )
        return

    text = textwrap.dedent(
        f"""
        <b>{name}</b>

        <b>Type→</b> {"Censored" if result["is_censored"] else "Uncensored"}
        <b>Released→</b> {result["released_date"].replace(" ", "-")}
        <b>Brand→</b> {result["brand"]}
        <b>Tags→</b> {" ".join(sorted(["#" + tag.replace(" ", "_") for tag in result["tags"]]))}
        """
    )

    if poster_url := result["poster_url"]:
        text += f"<a href='{poster_url}'>\xad</a>"

    description = BeautifulSoup(
        result.get("description", ""), "html.parser"
    ).text.strip()
    if len(description) < 3500:
        text += f"\n<b>Synopsis→</b> <i>{description}</i>"
    else:
        synopsis_url = await post_to_telegraph(name, description)
        if synopsis_url:
            text += f"\n<b>Synopsis→</b> <a href='{synopsis_url}'><i>Read Here</i></a>"

    buttons = [
        InlineKeyboardButton(f'{stream["height"]}p', url=stream["url"])
        for stream in reversed(result["streams"])
        if stream["url"]
    ]
    buttons = [buttons]

    if callback.from_user.id in ALLOWED_USERS:
        buttons.append(
            [
                InlineKeyboardButton(
                    "Send Bulk", f"hanime_bulk:{hanime_id}:{callback.from_user.id}"
                )
            ]
        )

    for button in callback.message.reply_markup.inline_keyboard[-1]:
        if "Next Page" in button.text or "Previous Page" in button.text:
            splited = button.callback_data.split(":")
            page = (
                int(splited[2]) + 1
                if "Previous" in button.text
                else int(splited[2]) - 1
            )
            splited[2] = str(page)
            back_data = ":".join(splited)
            break
    else:
        back_data = f"hanime_s:{query_id}:0:{callback.from_user.id}"

    buttons.append([InlineKeyboardButton("⟨ Back ⟩", back_data)])
    await callback.answer()
    await callback.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^hanime_bulk:.*"))
async def bulk_hanime(client, callback):
    user_id = str(callback.from_user.id)
    if user_id not in callback.data:
        return await callback.answer(
            "Sorry, this button is not for you.",
            show_alert=True,
        )

    hanime_id = callback.data.split(":")[1]
    user_filter = filters.user(callback.from_user.id)
    filters_ = user_filter & filters.text

    try:
        details = await HanimeTV.details(hanime_id)
        hanimetv_data = details["hanimetv"]
    except Exception:
        return await callback.answer(
            "Error When Fetching Details. Try again later!", show_alert=True
        )
    else:
        await callback.answer()

    request, response = await ask_message(
        callback.message,
        "Give me the ID of the chat where you want to send this hentai.",
        quote=False,
        filters=filters_ & non_command_filter,
    )
    try:
        chat_to_send = int(response.text)
        temp_msg = await client.send_message(chat_to_send, "Test Message")
        await temp_msg.delete()
    except ValueError:
        await request.edit("Chat ID should be a valid integer.")
        return
    except Exception:
        await request.edit(
            "Double-check if the ID you provided is correct or if I'm added to the chat with the right permissions."
        )
        return

    request, response = await ask_message(
        response,
        "If you want to have a custom filename, then write me the filename format. Send /skip to set the default.\n\n"
        "Variables you can use for bot to fill in the value:\n"
        "→<code>{name}</code>\n"
        "→<code>{episode}</code>\n"
        "→<code>{quality}</code>\n\n"
        "Example: <code>EP - {episode} {name} {quality}</code>",
        quote=True,
        filters=filters_,
    )
    if response.text.split()[0].lower() == "/skip":
        filename = "EP - {episode} {name} {quality}"
    else:
        filename = response.text.strip()

    request, response = await ask_message(
        response,
        "Do you want to send the files as <code>Video</code> or <code>Document</code>?",
        quote=True,
        filters=filters_ & non_command_filter,
    )
    upload_mode = response.text.lower()
    if upload_mode not in ("video", "document"):
        upload_mode = "document"

    request, response = await ask_message(
        response,
        "If you want to set your thumbnail on files, send me a photo Or write 'Yes' to use the default bot thumb Or use /skip to skip this step.",
        quote=True,
        filters=user_filter & (filters.text | filters.photo),
    )
    if response.photo:
        thumb = await response.download("cache/")
    elif response.text.lower() == "yes":
        thumb = "thumb.jpg"
    else:
        thumb = None

    request, response = await ask_message(
        response,
        "Do you want to upload the entire series? Answer in Yes or No.",
        quote=True,
        filters=filters_ & non_command_filter,
    )
    do_franchise = response.text.lower() == "yes"

    fetched_episodes, hstream_ep_link = [], None
    if len(details.get("hq_streams", [])) != 2:
        request, response = await ask_message(
            response,
            f"Provide the hentai link from hstream.moe {'(the /hentai/<hentai-id> link, not the /hentai/<hentai-id-episode> link)' if do_franchise else '(the /hentai/<hentai-id-episode> link, not the /hentai/<hentai-id> link)'} if you want higher quality, otherwise send /skip.",
            quote=True,
            filters=filters_ & non_command_filter,
        )
        hstream_link = response.text
        if hstream_link.lower() != "/skip":
            if do_franchise:
                try:
                    fetched_episodes = await AioHttp.request(
                    f"https://hdome.koyeb.app/api/hstream/get_episodes?url={hstream_link}&api_key=YATO.HENTI.GOD",
                    re_json=True,
                    )
                    assert isinstance(fetched_episodes, list) and fetched_episodes
                except Exception as e:
                    await request.edit(f"Not Found: {e}")
                else:
                    await request.edit(f"Found {len(fetched_episodes)} episodes.")
            else:
                hstream_ep_link = hstream_link

    status_msg = await response.reply("Please wait, processing...", quote=True)

    if do_franchise:
        hanimes = list(map(lambda d: d["id"], hanimetv_data["franchise_videos"])) or [
            details
        ]
    else:
        hanimes = [details]

    for ep_no, hanime in enumerate(hanimes, start=1):
        try:
            details = (
                await HanimeTV.details(hanime) if isinstance(hanime, int) else hanime
            )
            hanimetv_data = details["hanimetv"]
            hq_streams = details.get("hq_streams", [])
            if not details.get("hq_streams", []):
                hstream_ep_link = (
                    fetched_episodes[ep_no - 1]
                    if len(fetched_episodes) >= (ep_no - 1)
                    else None
                ) if not hstream_ep_link else hstream_ep_link
                if fetched_episodes and not hstream_ep_link:
                    request, response = await ask_message(
                        response,
                        f"Provide the hentai-episode link of ep - {ep_no} from hstream.moe if you want higher quality, otherwise send /skip.",
                        quote=True,
                        filters=filters_ & non_command_filter,
                    )
                    hstream_ep_link = (
                        response.text
                        if response.text.split()[0].lower() != "/skip"
                        else None
                    )
                if hstream_ep_link:
                    hstream_data = await AioHttp.request(
                        f"https://hdome.koyeb.app/api/hstream/get_details?url={hstream_ep_link}&api_key=YATO.HENTI.GOD"
                    )["streams"]
                    hq_streams = list(
                        filter(lambda x: x["resolution"] != "720p", hq_streams)
                    )
            if len(hanimes) == 1:
                ep_no = hanimetv_data["name"].split()[-1]
            if thumb is None and upload_mode == "document":
                thumb, *_ = await AioHttp.download(hanimetv_data["poster_url"])
            ytdl_opts = {
                "concurrent_fragment_downloads": 10,
                "retries": 20,
                "noplaylist": True,
            }
            await client.send_cached_media(
                chat_to_send,
                "CAACAgEAAxkBAAECLtxmLM42_Zxg5yUyHxfxy1-GVg5ElAACawEAAhHDIUeDS4rTR-6HMB4E",
            )
            await client.send_message(
                chat_to_send,
                f"<b>Episode:</b> <code>{ep_no}</code>",
            )
            for stream in reversed(hanimetv_data["streams"]):
                quality, url = f'{stream["height"]}p', stream["url"]
                if url == "":
                    continue
                file = (
                    os.path.join(
                        "cache/",
                        filename.format(
                            name=hanimetv_data["name"], episode=ep_no, quality=quality
                        ),
                    )
                    + ".mp4"
                )
                await status_msg.edit(
                    f'Downloading {hanimetv_data["name"]} - {quality}...'
                )
                ytdl_opts["outtmpl"] = file
                with YoutubeDL(ytdl_opts) as ytdl:
                    await retry_func(async_wrap(ytdl.download), [url], no_output=True)
                if os.path.exists(file):
                    await send_media(
                        upload_mode,
                        chat_to_send,
                        file,
                        caption=f"<i>{quality}</i>",
                        message=status_msg,
                        progress_user=callback.from_user.id,
                        thumb=thumb,
                    )
                    os.remove(file)
                await asyncio.sleep(3)
            for hq_stream in sorted(hq_streams, key=lambda x: x["resolution"]):
                file = (
                    os.path.join(
                        "cache/",
                        filename.format(
                            name=hanimetv_data["name"],
                            episode=ep_no,
                            quality=hq_stream["resolution"],
                        ),
                    )
                    + ".mp4"
                )
                await status_msg.edit(
                    f'Downloading {hanimetv_data["name"]} - {hq_stream["resolution"]}...'
                )
                if hq_stream.get("tg_message_id"):
                    file = await (
                        await client.ub.get_messages(-1002138040280, stream_mid)
                    ).download(file)
                else:
                    ytdl_opts["outtmpl"] = file
                    with YoutubeDL(ytdl_opts) as ytdl:
                        await retry_func(
                            async_wrap(ytdl.download),
                            [hq_stream["link"]],
                            no_output=True,
                        )
                    _file = file
                    file = file.replace("cache/", "")
                    ffmpeg_cmd = [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i" f'"{_file}"',
                        "-i",
                        f'"{hstream_data["subtitle"]}"',
                        "-c:v",
                        "copy",
                        "-c:a",
                        "copy",
                        "-c:s",
                        "mov_text",
                        "-strict",
                        "-2",
                        f'"{file}"',
                        "-y",
                    ]
                    await run_cmd(" ".join(ffmpeg_cmd))
                    os.remove(_file)
                await send_media(
                    "DOCUMENT",
                    chat_to_send,
                    file,
                    caption=f"<i>{hq_stream['resolution']}</i>",
                    message=status_msg,
                    progress_user=callback.from_user.id,
                    thumb=thumb,
                )
                os.remove(file)
            if thumb and thumb != "thumb.jpg":
                os.remove(thumb)
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await status_msg.edit(f"An error occurred: {str(e)}")
            return

    await status_msg.edit("Hentai files sent successfully.")


@Client.on_callback_query(filters.regex(r"^close.*"))
async def close_query(client, callback):
    splited = callback.data.split(":")
    if len(splited) > 1:
        btn_user = int(splited[1])
        if btn_user != callback.from_user.id:
            return await callback.answer(
                "Sorry, this button is not for you.", show_alert=True
            )

    await callback.answer()
    if not callback.data.startswith("close^na"):
        await callback.message.delete()
