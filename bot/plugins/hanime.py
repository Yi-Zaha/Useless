import asyncio
import json
import secrets
import textwrap
from dateutil import parser
from typing import Union

from bs4 import BeautifulSoup
from pyrogram import filters
from pyrogram.types import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup

from bot import ALLOWED_USERS, bot
from bot.utils import non_command_filter
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.functions import get_random_id, post_to_telegraph


cache = {}


class HanimeTV:
    SEARCH_URL = "https://search.htv-services.com"
    HANIME_API_URL = "https://hanime.tv/api/v8"
    HANIME_API_TOKEN = "PhzIzReFsg7g2GZi-tz9KVpR2LskgMP8-l_xJ0kmbwhSuBOcD3yZJeOoQKS-ND1w3qFCGj0Y2HzfJ4renU82W25BNSVI6KnmwfiN5e9lueyQOYbZ0RVKmS2Ek1fLKvMnS_3ktEUiFOTjSCezPusemw==(-(0)-)hDLS0eC_45mNW15pn3ZJYQ=="
    
    @staticmethod
    async def search(query: str, page: int = 0, tags: str = None, brands: str = None, blacklist: str = None,
                 order_by: str = None, ordering: str = None):
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

        response_data = await AioHttp.request(HanimeTV.SEARCH_URL, "POST", headers=headers, json=search_data, re_json=True)
    
        return {
            "response": json.loads(response_data['hits']),
            "page": response_data['page'],
            "total_pages": response_data['nbPages']
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

        response_data = await AioHttp.request(HanimeTV.SEARCH_URL, "POST", headers=headers, json=search_data, re_json=True)

        return {
            "response": json.loads(response_data['hits']),
            "page": response_data['page'],
            "total_pages": response_data['nbPages']
        }

    @staticmethod
    async def trending(time: str = "month", page: int = 0):
        headers = {"X-Signature-Version": "web2",
               "X-Signature": secrets.token_hex(32)}

        response_data = await AioHttp.request(f"{HanimeTV.HANIME_API_URL}/browse-trending?time={time}&page={page}", headers=headers, re_json=True)

        return response_data

    @staticmethod
    async def details(id: Union[int, str]):
        headers = {"X-Session-Token": HanimeTV.HANIME_API_TOKEN}
        response_data = await AioHttp.request(f"{HanimeTV.HANIME_API_URL}/video?id={id}", headers=headers, re_json=True)

        created_at = parser.parse(
            response_data["hentai_video"]["created_at"]).strftime("%Y %m %d")
        released_date = parser.parse(
            response_data["hentai_video"]["released_at"]).strftime("%Y %m %d")
        views = "{:,}".format(response_data["hentai_video"]["views"])
        tags = [tag["text"].title()
                for tag in response_data["hentai_video"]["hentai_tags"]]
        streams = response_data["videos_manifest"]["servers"][0]["streams"]

        video_details = {
            "id": response_data["hentai_video"]["id"],
            "query": response_data["hentai_video"]["slug"],
            "name": response_data["hentai_video"]["name"],
            "description": response_data["hentai_video"]["description"],
            "brand": response_data["hentai_video"]["brand"],
            "franchise": response_data["hentai_franchise"],
            "franchise_videos": response_data["hentai_franchise_hentai_videos"],
            "poster": response_data["hentai_video"]["cover_url"],
            "thumbnail": response_data["hentai_video"]["poster_url"],
            "screenshots": response_data["hentai_video_storyboards"][0]["url"],
            "views": views,
            "streams": streams,
            "created_at": created_at,
            "released_date": released_date,
            "is_censored": response_data["hentai_video"]["is_censored"],
            "tags": tags,
            "next": response_data["next_hentai_video"],
            "next_random": response_data["next_random_hentai_video"]
        }

        return video_details

    @staticmethod
    async def link(id: Union[int, str]):
        headers = {"X-Session-Token": HanimeTV.HANIME_API_TOKEN}
        response_data = await AioHttp.request(f"{HanimeTV.HANIME_API_URL}/video?id={id}", headers=headers, re_json=True)

        streams = response_data["videos_manifest"]["servers"][0]["streams"]

        return streams


@bot.on_message(filters.command("hentai") & filters.user(ALLOWED_USERS))
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
        status = await query_message.reply("Searching...")
    else:
        query = " ".join(message.command[1:])
        status = await message.reply("Searching...")

    query_id = get_random_id()
    cache[query_id] = query
    await search_query(
        client, status, query_id=query_id, page=0, button_user=message.from_user.id
    )


@bot.on_callback_query(filters.regex(r"^hanime_s:.*"))
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


@bot.on_callback_query(filters.regex(r"^hanime_i:.*"))
async def hanime_query(client, callback):
    hanime_id, query_id = callback.data.split(":")[1:3]
    if str(callback.from_user.id) not in callback.data:
        return await callback.answer(
            "This button can only be used by the one who issued the command.",
            show_alert=True,
        )

    try:
        result = await HanimeTV.details(hanime_id)
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
        <b>Tags→</b> {", ".join(sorted(result["tags"]))}
        """
    )

    poster_url = result["poster"]
    if poster_url:
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


@bot.on_callback_query(filters.regex(r"^close.*"))
async def close_query(client, callback):
    splited = callback.data.split(":")
    if len(splited) > 1:
        btn_user = int(splited[1])
        if btn_user != callback.from_user.id:
            return await callback.answer(
                "Sorry, this button is not for you.", show_alert=True
            )

    await callback.answer()
    await callback.message.delete()
