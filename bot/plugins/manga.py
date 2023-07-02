import asyncio
import os
import re

import cachetools
from pyrogram import filters
from pyrogram.enums import ChatAction
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
)

from bot import ALLOWED_USERS, bot
from bot.helpers.manga import IManga
from bot.helpers.psutils import zeroint
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.db import dB
from bot.utils.functions import get_chat_link_from_msg, post_to_telegraph, split_list

Process = {}
Bulk = set()
manga_cache = cachetools.TTLCache(maxsize=1024, ttl=10 * 60)


@bot.on_message(filters.command("getmanga") & filters.user(ALLOWED_USERS))
async def manganato_search(client, message):
    if len(message.command) == 1:
        return await message.reply("What should I do? Give me a query to search for.")

    query = " ".join(message.command[1:])

    status = await message.reply("Searching...")
    try:
        result = await AioHttp.request(
            "https://manganato.com/getstorysearchjson",
            "post",
            data={"searchword": query},
            re_json=True,
        )
        assert result["searchlist"]
    except Exception:
        return await status.edit("No result found for the given query.")

    data = {}
    regex = re.compile(r"<span .*?>(.+?)</span>")

    for item in result["searchlist"]:
        name = item["name"]
        while "</span>" in name:
            name = re.sub(regex, r"\1", name)
        data[name.title().replace("'S", "'s")] = item["url_story"].split("/")[-1]

    buttons = [
        [InlineKeyboardButton(title, f"manganl_{message.from_user.id}_{manga_id}")]
        for title, manga_id in data.items()
    ]

    await status.edit(
        f"Search results for `{query}`.", reply_markup=InlineKeyboardMarkup(buttons)
    )


@bot.on_callback_query(filters.regex(r"^manganl_(.*)"))
async def manganl_query(client, callback):
    splited = callback.data.split("_")
    manga_id = splited[-1]
    btn_user = None

    if len(splited) == 3:
        btn_user = int(splited[1])
        if btn_user != callback.from_user.id:
            return await callback.answer(
                "Sorry, this button is not for you.", show_alert=True
            )

    manga = await get_manga(manga_id)
    chapters = list(manga.chapters.keys())[-1]
    authors = ", ".join(sorted(manga.authors))
    genres = ", ".join(sorted(manga.genres))

    description = await post_to_telegraph(manga.title.strip(), manga.description)

    caption = f"""<b>{manga.title}</b>

<b>Alternative(s) :</b> {manga.alternatives}
<b>→ID :</b> <code>{manga.id}</code>
<b>→Views :</b> {manga.views}
<b>→Status :</b> {manga.status}
<b>→Updated :</b> {manga.updated}
<b>→Chapters :</b> {chapters}
<b>→Authors :</b> {authors}
<b>→Genres :</b> {genres}

<b>[Synopsis]({description})</b>"""

    buttons = [
        InlineKeyboardButton(
            "Download",
            f"mpage:{manga_id}:0" if not btn_user else f"mpage:{btn_user}:{manga_id}:0",
        )
    ]

    await client.send_photo(
        callback.message.chat.id,
        manga.poster_url,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([buttons]),
    )

    await callback.answer()
    await callback.message.delete()


@bot.on_message(filters.command("mread") & filters.user(ALLOWED_USERS))
async def read_manga(client, message):
    if len(message.command) == 1:
        return await message.reply("Give manga ID and chapter number.")

    text = " ".join(message.command[1:])

    is_thumb = "-thumb" in text
    nelo = "-nelo" in text
    mode = "pdf" if "-pdf" in text else "cbz"
    flags = ("-thumb", "-nelo", "-pdf", "-protect")

    for flag in flags:
        text = text.replace(flag, "").strip()

    manga_id, chapter_no = text.split(" ", 1)

    try:
        manga = await get_manga(manga_id, nelo=nelo)
    except Exception:
        return await message.reply("Manga ID not found.")

    if chapter_no not in manga.chapters:
        return await message.reply("Invalid chapter number.")

    status = await message.reply("Processing...")

    ch = zeroint(chapter_no)
    file_name = f"Ch - {ch} {manga.title}"

    thumb = await dl_mgn_thumb(manga) if is_thumb else None

    try:
        file = await IManga.dl_chapter(manga.chapters[chapter_no], file_name, mode)

        K = await client.send_document(
            message.chat.id,
            file,
            caption=f"**{manga.title}\nChapter - {ch}**",
            thumb=thumb,
        )

        await status.delete()
        os.remove(file)
    except Exception as e:
        await status.edit(
            f"**Something Went Wrong❗**\n\n`{e.__class__.__name__} : {e}`"
        )


@bot.on_message(filters.command("mbulk") & filters.user(ALLOWED_USERS))
async def bulk_manga(client, message):
    if len(message.command) == 1:
        return await message.reply("Give manga ID.")

    text = " ".join(message.command[1:])
    is_thumb = "-thumb" in text
    nelo = "-nelo" in text
    mode = "pdf" if "-pdf" in text else "cbz"
    protect = "-protect" in text
    flags = ("-thumb", "-nelo", "-pdf", "-protect")

    for flag in flags:
        text = text.replace(flag, "").strip()

    manga_id = text
    chat = message.chat.id

    if " | " in text:
        manga_id, chat = text.split(" | ", 1)
        manga_id = manga_id.strip()
        chat = chat.strip()

    try:
        manga = await get_manga(manga_id, nelo=nelo)
    except Exception:
        return await message.reply("Invalid Manga ID.")

    status = await message.reply("Processing...")

    thumb = await dl_mgn_thumb(manga) if is_thumb else None

    ch_msg = None
    _edited = False
    here = None

    id = f"cancelbulk:{message.from_user.id}:{chat}:{manga_id}"
    Bulk.add(id)

    button = [InlineKeyboardButton("Cancel", id)]
    markup = InlineKeyboardMarkup([button])

    for ch in manga.chapters:
        if id not in Bulk:
            return await status.edit("Upload Cancelled!")

        if ch_msg and not _edited:
            here = await get_chat_link_from_msg(ch_msg)
            await status.edit(
                f"Bulk uploading {list(manga.chapters)[-1]} chapters of [{manga.title}]({manga.url}) in [here.]({here})",
                reply_markup=markup,
            )

            _edited = True

        try:
            url = manga.chapters[ch]
            ch = zeroint(ch)
            title = f"Ch - {ch} {manga.title}"

            file = await IManga.dl_chapter(url, title, mode)
            ch_msg = await client.send_document(
                int(chat), file, thumb=thumb, protect_content=protect
            )
            os.remove(file)
        except Exception as e:
            Bulk.remove(id)
            await status.edit(
                f"**Something Went Wrong❗**\n\n`{e.__class__.__name__} : {e}`"
            )
            return

        await asyncio.sleep(2)

    if thumb:
        os.remove(thumb)

    if id in Bulk:
        Bulk.remove(id)

    await status.edit(
        f"Successfully bulk uploaded {list(manga.chapters)[-1]} chapters of [{manga.title}]({manga.url}) in [here.]({here})"
    )


@bot.on_callback_query(filters.regex(r"^cancelbulk:(.*)"))
async def cancelbulk_query(client, callback):
    if str(callback.from_user.id) not in callback.data:
        return await callback.answer(
            "Sorry, this button is not for you.", show_alert=True
        )

    if callback.data in Bulk:
        Bulk.remove(callback.data)
        await callback.answer("This process will be cancelled soon!", show_alert=True)
    else:
        await callback.answer("This process is not active anymore.", show_alert=True)
        await callback.message.delete()


@bot.on_callback_query(filters.regex("^mpage:(.*)$"))
async def mpage_query(client, callback):
    _, btn_user, manga_id, page = callback.data.split(":")

    if int(btn_user) != callback.from_user.id:
        return await callback.answer(
            "Sorry, this button is not for you.", show_alert=True
        )

    page = int(page)
    try:
        total_pages, chapters = await get_page_chapters(manga_id, page=page)
    except BaseException:
        return await callback.answer("No chapters there!")

    buttons = [
        InlineKeyboardButton(str(i), f"mgdl:{btn_user}:{manga_id}:{i}")
        for i in chapters
    ]
    buttons = split_list(buttons, 4)
    back_button = [
        InlineKeyboardButton(
            "« Back",
            f"mpage:{btn_user}:{manga_id}:{page - 1 if page != 0 else total_pages - 1}",
        )
    ]
    curr_button = [InlineKeyboardButton(f"Page {page}", f"close_{btn_user}")]
    next_button = [
        InlineKeyboardButton(
            "Next »",
            f"mpage:{btn_user}:{manga_id}:{page + 1 if page != total_pages - 1 else 0}",
        )
    ]
    buttons += [back_button + curr_button + next_button]

    await callback.edit_message_reply_markup(InlineKeyboardMarkup(buttons))
    await callback.answer()


@bot.on_callback_query(filters.regex("^mgdl:(.*)"))
async def mangadl_handler(client, callback):
    _, btn_user, manga_id, ch = callback.data.split(":")

    if int(btn_user) != callback.from_user.id:
        return await callback.answer(
            "Sorry, this button is not for you.", show_alert=True
        )

    db_key = f"mangafiles:{manga_id}:{ch}"

    if callback.from_user.id not in Process:
        Process[callback.from_user.id] = []

    db_entry = await dB.get_key(db_key, re_doc=True)
    if db_entry:
        caption = db_entry.get("caption")
        pdf = InputMediaDocument(db_entry.get("pdf"))
        cbz = InputMediaDocument(db_entry.get("cbz"), caption=f"<b>{caption}</b>")
        await client.send_media_group(callback.message.chat.id, [pdf, cbz])
        await callback.answer()
        return

    if manga_id in Process[callback.from_user.id]:
        return await callback.answer(
            "This manga is already in process.\nPlease wait for it to be completed!",
            show_alert=True,
        )

    Process[callback.from_user.id].append(manga_id)
    await callback.answer("Downloading....", show_alert=True)

    try:
        manga = await get_manga(manga_id)
        ch_url = manga.chapters[ch]
        ch = zeroint(ch)
        ch_name = f"cache/Ch - {ch} {manga.title.strip()[:40]}"
        thumb = await dl_mgn_thumb(manga)
        caption = f"<b>{manga.title}\nChapter - {ch}</b>"
        pdf_file, cbz_file = await IManga.dl_chapter(ch_url, ch_name, "both")

        await client.send_chat_action(
            callback.message.chat.id, ChatAction.UPLOAD_DOCUMENT
        )
        pdf = InputMediaDocument(pdf_file, thumb=thumb)
        cbz = InputMediaDocument(cbz_file, thumb=thumb, caption=caption)
        sent = await client.send_media_group(callback.message.chat.id, [pdf, cbz])

        await dB().insert_one(
            {
                db_key: True,
                "pdf": sent[0].document.file_id,
                "cbz": sent[1].document.file_id,
                "caption": str(cbz.caption),
            }
        )
        await client.send_chat_action(callback.message.chat.id, ChatAction.CANCEL)
        os.remove(pdf_file)
        os.remove(cbz_file)
    finally:
        Process[callback.from_user.id].remove(manga_id)


async def get_manga(manga_id, nelo=False, refresh=False):
    cache_key = manga_id + str(nelo)
    if cache_key in manga_cache and not refresh:
        return manga_cache[cache_key]

    manga = await IManga(manga_id, nelo=nelo)._parse_info()
    manga_cache[cache_key] = manga
    return manga


async def get_page_chapters(manga_id, page=0, nelo=False):
    manga = await get_manga(manga_id, nelo=nelo)
    chapters_page = split_list(list(manga.chapters), 30)
    return len(chapters_page), chapters_page[page]


async def dl_mgn_thumb(manga):
    try:
        thumb_path = os.path.join("cache", os.path.basename(manga.poster_url))
        if not os.path.exists(thumb_path):
            await AioHttp.download(manga.poster_url, filename=thumb_path)
    except BaseException:
        return None

    return thumb_path
