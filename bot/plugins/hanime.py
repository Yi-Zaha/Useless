import asyncio
import textwrap
from urllib.parse import quote

from bs4 import BeautifulSoup
from pyrogram import filters
from pyrogram.types import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup

from bot import bot
from bot.utils import non_command_filter
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.functions import get_random_id, post_to_telegraph

API_URL = "https://hanime-tv-api-e0e67be02b15.herokuapp.com"
cache = {}


@bot.on_message(filters.command("hentai"))
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
        result = await AioHttp.request(
            f"{API_URL}/search?query={cache[query_id]}&page={page}", re_json=True
        )
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
        result = await AioHttp.request(
            f"{API_URL}/details?id={hanime_id}", re_json=True
        )
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

    poster_url = result.get("poster")
    if poster_url:
        last_part = poster_url.split("/")[-1]
        poster_url = poster_url.replace(last_part, quote(last_part))
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
            page = int(splited[2]) + 1 if "Previous" in button.text else int(splited[2]) - 1
            splited[2] = str(page)
            back_data = ":".join(splited)
            break
    else:
        back_data = f"hanime_s:{query_id}:0:{callback.from_user.id}"

    buttons.append([InlineKeyboardButton("⟨ Back ⟩", back_data)])
    await callback.answer()
    await callback.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@bot.on_callback_query(filters.regex(r"^close$"))
async def close_query(client, callback):
    splited = callback.data.split("_")
    if len(splited) > 1:
        btn_user = int(splited[1])
        if btn_user != callback.from_user.id:
            return await callback.answer(
                "Sorry, this button is not for you.", show_alert=True
            )

    await callback.answer()
    await callback.message.delete()
