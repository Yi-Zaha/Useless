import os

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import SUDOS, bot
from bot.helpers import ani
from bot.utils import channel_filter
from bot.utils.aiohttp_helper import AioHttp


@bot.on_message(filters.command("anime") & channel_filter)
async def anime_search(client, message):
    if message.from_user and message.from_user.id not in SUDOS:
        return

    if len(message.command) == 1:
        return await message.reply("What should I do? Give me a query to search for.")

    query = " ".join(message.command[1:])

    animes, _ = await ani.searchanilist(query, manga=False)
    if not animes:
        return await message.reply("No results found for the given query.")

    buttons = [
        [
            InlineKeyboardButton(
                anime["title"]["english"] or anime["title"]["romaji"],
                f"anime_{anime['id']}"
                if not message.from_user
                else f"anime_{message.from_user.id}_{anime['id']}",
            )
        ]
        for anime in animes
    ]

    await message.reply(
        f"Search results for `{query}`.", reply_markup=InlineKeyboardMarkup(buttons)
    )

    if not message.from_user:
        await message.delete()


@bot.on_message(filters.command("manga") & channel_filter)
async def manga_search(client, message):
    if message.from_user and message.from_user.id not in SUDOS:
        return

    if len(message.command) == 1:
        return await message.reply("What should I do? Give me a query to search for.")

    query = " ".join(message.command[1:])

    mangas, _ = await ani.searchanilist(query, manga=True)
    if not mangas:
        return await message.reply("No results found for the given query.")

    buttons = [
        [
            InlineKeyboardButton(
                manga["title"]["english"] or manga["title"]["romaji"],
                f"manga_{manga['id']}"
                if not message.from_user
                else f"manga_{message.from_user.id}_{manga['id']}",
            )
        ]
        for manga in mangas
    ]

    await message.reply(
        f"Search results for `{query}`.", reply_markup=InlineKeyboardMarkup(buttons)
    )

    if not message.from_user:
        await message.delete()

@bot.on_message(filters.command("pmanga") & channel_filter)
async def manga_search(client, message):
    if message.from_user and message.from_user.id not in SUDOS:
        return

    if len(message.command) == 1:
        return await message.reply("What should I do? Give me a query to search for.")

    query = " ".join(message.command[1:])

    mangas, _ = await ani.searchanilist(query, manga=True)
    if not mangas:
        return await message.reply("No results found for the given query.")

    buttons = [
        [
            InlineKeyboardButton(
                manga["title"]["english"] or manga["title"]["romaji"],
                f"pmanga_{manga['id']}"
                if not message.from_user
                else f"pmanga_{message.from_user.id}_{manga['id']}",
            )
        ]
        for manga in mangas
    ]

    await message.reply(
        f"Search results for `{query}`.", reply_markup=InlineKeyboardMarkup(buttons)
    )

    if not message.from_user:
        await message.delete()


@bot.on_callback_query(filters.regex(r"^anime_.*"))
async def anime_query(client, callback):
    splited = callback.data.split("_")
    ani_id = splited[-1]

    if len(splited) == 3:
        btn_user = int(splited[1])
        if btn_user != callback.from_user.id:
            return await callback.answer(
                "Sorry, this button is not for you.", show_alert=True
            )

    text, image, reply_markup = await ani.get_anime_manga(None, "anime_anime", ani_id)
    await callback.answer("Processing...")
    image_path = f"cache/anilist_img-{ani_id}.png"

    if not os.path.exists(image_path):
        await AioHttp.download(image, filename=image_path)

    await client.send_photo(
        callback.message.chat.id,
        image_path,
        caption=text,
        reply_markup=reply_markup,
    )
    await callback.message.delete()


@bot.on_callback_query(filters.regex(r"^(p|)manga_.*"))
async def manga_query(client, callback):
    splited = callback.data.split("_")
    ani_id = splited[-1]

    if len(splited) == 3:
        btn_user = int(splited[1])
        if btn_user != callback.from_user.id:
            return await callback.answer(
                "Sorry, this button is not for you.", show_alert=True
            )
    
    if splited[0].startswith("p"):
        text, image = await ani.get_pmanga(id=ani_id)
        await client.send_photo(callback.message.chat.id, image, caption=text)
        return

    text, image, reply_markup = await ani.get_anime_manga(None, "anime_manga", ani_id)
    await callback.answer("Processing...")
    image_path = f"cache/anilist_img-{ani_id}.png"

    if not os.path.exists(image_path):
        await AioHttp.download(image, filename=image_path)

    await client.send_photo(
        callback.message.chat.id,
        image_path,
        caption=text,
        reply_markup=reply_markup,
    )
    await callback.message.delete()
