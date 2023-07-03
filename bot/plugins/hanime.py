import os

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import bot
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.functions import post_to_telegraph

API_URL = "https://hanime-tv-api-tau.vercel.app"


@bot.on_message(filters.command("hentai"))
async def search_hentai(client, message):
    if len(message.command) == 1:
        return await message.reply("What should I do? Give me a query to search for.")

    query = " ".join(message.command[1:])

    try:
        result = await AioHttp.request(
            f"{API_URL}/search?query={query}&page=0", re_json=True
        )
        assert result["response"]
    except Exception:
        return await message.reply("No result found for the given query.")

    buttons = [
        [
            InlineKeyboardButton(
                res["name"],
                f"hanime_{res['id']}"
                if not message.from_user
                else f"hanime_{message.from_user.id}_{res['id']}",
            )
        ]
        for res in result["response"]
    ]

    await message.reply(
        f"Search results for `{query}`.", reply_markup=InlineKeyboardMarkup(buttons)
    )


@bot.on_callback_query(filters.regex(r"^hanime_(.*)"))
async def hanime_info(client, callback):
    splited = callback.data.split("_")
    hanime_id = splited[-1]
    btn_user = None

    if len(splited) == 3:
        btn_user = int(splited[1])
        if btn_user != callback.from_user.id:
            return await callback.answer(
                "Sorry, this button is not for you.", show_alert=True
            )

    try:
        result = await AioHttp.request(
            f"{API_URL}/details?id={hanime_id}", re_json=True
        )
        assert result["name"]
    except Exception:
        return await callback.answer(
            "An error occurred. Please try again later!", show_alert=True
        )

    name = result["name"]
    release_date = result["released_date"].replace(" ", "-")
    censor = "Censored" if result["is_censored"] else "Uncensored"
    brand = result["brand"]
    tags = ", ".join(sorted(result["tags"]))
    description_id = await post_to_telegraph(name, result["description"] or "N/A")
    description = f"<a href='{description_id}'><b>Synopsis</b></a>"
    poster_url = result["poster"]

    caption = (
        f"<b>{name}</b> [{censor}]\n\n"
        f"<b>››Release Date</b>: <i>{release_date}</i>\n"
        f"<b>››Studio</b>: <i>{brand}</i>\n"
        f"<b>››Genres</b>: <i>{tags}</i>\n\n"
        f"{description}"
    )

    button = [
        InlineKeyboardButton(
            "Watch",
            f"hanimelinks_{hanime_id}"
            if not btn_user
            else f"hanimelinks_{btn_user}_{hanime_id}",
        )
    ]

    try:
        await client.send_photo(
            callback.message.chat.id,
            poster_url,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([button]),
        )
    except BaseException:
        file = (await AioHttp.download(poster_url))[0]
        await client.send_photo(
            callback.message.chat.id,
            file,
            caption=caption,
            reply_markup=InlineKeyboardMarkup([button]),
        )
        os.remove(file)

    await message.answer()


@bot.on_callback_query(filters.regex(r"^hanimelinks_(.*)"))
async def hanime_links(client, callback):
    splited = callback.data.split("_")
    hanime_id = splited[-1]

    if len(splited) == 3:
        btn_user = int(splited[1])
        if btn_user != callback.from_user.id:
            return await callback.answer(
                "Sorry, this button is not for you.", show_alert=True
            )

    try:
        result = await AioHttp.request(f"{API_URL}/link?id={hanime_id}", re_json=True)
        assert result["data"]
    except Exception:
        return await callback.answer(
            "An error occurred. Please try again later!", show_alert=True
        )

    url = result["data"][0]["url"]

    if url:
        url1 = result["data"][0]["url"]
        url2 = result["data"][1]["url"]
        url3 = result["data"][2]["url"]
        buttons = [
            [
                InlineKeyboardButton("360p", url=f"{url3}"),
                InlineKeyboardButton("480p", url=f"{url2}"),
            ],
            [InlineKeyboardButton("720p", url=f"{url1}")],
        ]
    else:
        url1 = result["data"][1]["url"]
        url2 = result["data"][2]["url"]
        url3 = result["data"][3]["url"]
        buttons = [
            [
                InlineKeyboardButton("360p", url=f"{url3}"),
                InlineKeyboardButton("480p", url=f"{url2}"),
            ],
            [InlineKeyboardButton("720p", url=f"{url1}")],
        ]

    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
    await callback.answer()


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
