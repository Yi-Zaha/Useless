import asyncio
import io
import os
from datetime import datetime, timedelta

from html_telegraph_poster.upload_images import upload_image
from pyrogram import filters
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
)

from bot import ALLOWED_USERS, bot
from bot.helpers.manga import PS, IManga
from bot.helpers.psutils import ch_from_url, iargs, zeroint
from bot.logger import LOGGER
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.db import pdB
from bot.utils.functions import ask_msg, get_chat_invite_link

PH_LOG_CHAT = -1001848617769
DISABLED_PS = []
DELAYED_PS = ["Manhwa18", "Mangabuddy"]
PS_SLEPT = set()
CHAPTER_LOG_MSG = """
<i><b>#New_Chapter</b></i>
<i>→{title}
→{ch}</i>
"""


@bot.on_message(filters.command("msub") & filters.user(ALLOWED_USERS) & filters.private)
async def add_sub(client, message):
    req, res = await ask_msg(message, "Provide the manga URL")
    url = res.text.strip()

    try:
        ps = PS.guess_ps(url)
    except ValueError:
        return await res.reply("Invalid URL.")

    status = await res.reply("Processing...")
    try:
        title = await PS.get_title(url, ps=ps)
        lc = await pdB.get_lc(url)
        if not lc:
            agen = PS.iter_chapters(url, ps=ps)
            last_chapter = await anext(agen)
            await pdB.add_lc(url, last_chapter)
        else:
            last_chapter = lc["lc_url"]
    except Exception as e:
        return await status.edit(
            f"Oops, something went wrong!\n\n<code>{e.__class__.__name__}: {e}</code>"
        )
    await status.delete()

    req, res = await ask_msg(res, "Provide the chat ID.")
    chat = res.text.strip()

    try:
        chat = int(chat)
    except ValueError:
        return await res.reply("Chat ID should be an integer!")

    try:
        tmp = await client.send_message(chat, url)
        await tmp.delete()
    except BaseException:
        return await res.reply(
            "I am unable to send a message to the given chat. Please check my permissions!"
        )

    req, res = await ask_msg(
        res,
        "Tell me the mode of the file in which you want to receive updates.\n\n"
        "Choose between:\n"
        "- <code>PDF</code>\n"
        "- <code>CBZ</code>\n"
        "- <code>BOTH</code>\n\n",
    )
    file_mode = res.text.lower()
    if file_mode not in ("pdf", "cbz", "both"):
        return await res.reply("Invalid file mode.")

    req, res = await ask_msg(
        res,
        "Provide the custom filename.\n\n"
        "You must include these tags:\n"
        "- <code>{ch}</code>\n"
        "- <code>{manga}</code>\n"
        'Example: "<code>{ch} {manga}</code>"\n\n'
        "<i>/skip to skip this part.</i>",
    )
    custom_filename = res.text
    if custom_filename.lower().split(" ")[0] in ["/skip"]:
        custom_filename = None
    elif "{ch}" not in custom_filename:
        return await res.reply(
            "Invalid format. You should include the <code>{ch}</code> tag."
        )

    req, res = await ask_msg(
        res,
        "Provide the custom caption.\n\n"
        "You can include these tags (if you want to):\n"
        "- <code>{ch}</code>\n"
        "- <code>{manga}</code>\n\n"
        "<i>/skip to skip this part.</i>",
    )
    custom_caption = res.text.html
    if custom_caption.lower().split(" ")[0] in ["/skip"]:
        custom_caption = None

    req, res = await ask_msg(
        res,
        "Provide the thumbnail for chapter files.\n\n"
        "<i>/skip to skip this part.</i>",
        filters=(filters.text | filters.photo),
    )
    if res.text and res.text.lower().split(" ")[0] in ["/skip"]:
        thumb_url = None
    elif res.photo:
        tmp_file = await res.download()
        thumb_url = upload_image(tmp_file)
        os.remove(tmp_file)
    else:
        thumb_url = res.text

    req, res = await ask_msg(
        res,
        "Do you want to receive updates for this subscription?\n\n"
        "<i>Answer in Yes or No.</i>",
    )
    send_updates = res.text.lower() in ("yes", "true")

    await pdB.add_sub(
        ps,
        url,
        chat,
        title,
        send_updates=send_updates,
        file_mode=file_mode.upper(),
        custom_filename=custom_filename,
        custom_caption=custom_caption,
        thumb_url=thumb_url,
    )

    text = "**Added New Subscription**\n\n"
    text += f"**›› Url →** `{url}`\n"
    text += f"**›› Chat →** `{chat}`\n"
    text += f"**›› File Mode →** `{file_mode.upper()}`\n" if file_mode else ""
    text += f"**›› Custom Filename →** `{custom_filename}`\n" if custom_filename else ""
    text += f"**›› Custom Caption →** `{custom_caption}`\n" if custom_caption else ""
    text += f"**›› Custom Thumb →** `{thumb_url}`" if thumb_url else ""

    await message.reply(text, parse_mode=ParseMode.MARKDOWN)


@bot.on_message(
    filters.command("rmsub") & filters.user(ALLOWED_USERS) & filters.private
)
async def remove_sub(client, message):
    if len(message.command) < 3:
        return await message.reply(
            "You have to provide the URL and chat ID to remove a subscription."
        )

    url = message.command[1]
    chat = message.command[2]
    try:
        chat = int(chat)
    except ValueError:
        pass

    try:
        ps = PS.guess_ps(url)
    except ValueError:
        ps = None

    sub = await pdB.get_sub(ps, url, chat)
    if not sub:
        return await message.reply("No subscription found for the given information.")

    await pdB.rm_sub(ps, url, chat)
    await message.reply("Subscription removed successfully.")


@bot.on_message(filters.command("subs") & filters.user(ALLOWED_USERS) & filters.private)
async def list_all_subs(client, message):
    subs = dict()
    subs_count = 0

    async for sub in pdB.all_subs():
        ps = sub["ps"]
        url = sub["url"]
        chat = sub["chat"]
        title = sub["title"]

        if ps not in subs:
            subs[ps] = []

        s_text = f"\n• {title}\n" f"→ Url: {url}\n" f"→ Chat: {chat}\n"
        subs[ps].append(s_text)
        subs_count += 1

    text = ""
    for ps, lst in subs.items():
        text += f"{ps} ({len(lst)}):\n"
        for s_text in lst:
            text += s_text
        text += "\n\n"

    if len(text) > 4096:
        await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        with io.BytesIO(text.encode()) as file:
            file.name = "Subs.txt"
            await client.send_document(
                message.chat.id,
                file,
                caption=f"<b>Total Subs:</b> <code>{subs_count}</code>",
            )
        await client.send_chat_action(message.chat.id, ChatAction.CANCEL)
    else:
        text = f"<b>Total Subs:</b> <code>{subs_count}</code>\n\n" + text
        await message.reply(text)


@bot.on_message(filters.command("newch") & filters.user(ALLOWED_USERS))
async def newch_log(client, message):
    if len(message.command) == 1:
        return await message.reply("Invalid syntax for chapter log message.")

    text = " ".join(message.command[1:]).split(" | ")
    if len(text) not in (2, 3):
        return await message.reply("Invalid syntax for chapter log message.")

    title, ch = text[:2]
    chat = text[2] if len(text) == 3 else None

    try:
        chat_link = await get_chat_invite_link(chat)
    except BaseException:
        chat_link = None

    if _is_numeric(ch):
        ch = f"Chapter {ch}"
    log_msg = CHAPTER_LOG_MSG.format(title=title, ch=ch)
    reply_markup = None
    if chat_link:
        button = [InlineKeyboardButton("Read Here", url=chat_link)]
        reply_markup = InlineKeyboardMarkup([button])

    post = await client.send_message(PH_LOG_CHAT, log_msg, reply_markup=reply_markup)
    await message.reply(
        f"Posted new chapter dialog in [{post.chat.title}]({post.chat.link})."
    )


async def new_updates():
    ps_updates = {}
    all_updates = {}

    for ps in PS.__all__:
        ps_updates[ps] = await PS.updates(ps)

    async for lc in pdB.all_lcs():
        url = lc["url"]
        last_chapter = lc["lc_url"]

        for ps, updates in ps_updates.items():
            if ps not in all_updates:
                all_updates[ps] = {}

            if url in updates and updates[url] != last_chapter:
                new_chapters = []
                async for ch_url in PS.iter_chapters(url):
                    if ch_url == last_chapter or len(new_chapters) > 25:
                        break
                    new_chapters.append(ch_url)

                if new_chapters:
                    new_chapters.reverse()
                    all_updates[ps][url] = new_chapters

    return all_updates


async def update_subs():
    LOGGER(__name__).info("Updating PS Subs...")
    subs = [sub async for sub in pdB.all_subs()]
    subs_data = {}

    for sub in subs:
        url = sub["url"]
        chat = sub["chat"]
        title = sub["title"]
        send_updates = sub["send_updates"] or False
        file_mode = sub["file_mode"] or "pdf"
        custom_filename = sub["custom_filename"] or "{ch} {manga}"
        custom_caption = sub["custom_caption"] or ""
        custom_thumb = sub["custom_thumb"] or False

        if url not in subs_data:
            subs_data[url] = []

        subs_data[url].append(
            (
                chat,
                title,
                send_updates,
                file_mode,
                custom_filename,
                custom_caption,
                custom_thumb,
            )
        )

    for ps, updates in (await new_updates()).items():
        LOGGER(__name__).info(f"Checking for PS: {ps}")

        if updates and ps in DELAYED_PS:
            if ps not in PS_SLEPT:
                PS_SLEPT.add(ps)
                await asyncio.sleep(10 * 60)
                return await update_subs()
            else:
                PS_SLEPT.remove(ps)

        for url, new_chapters in updates.items():
            if url not in subs_data:
                await pdB.add_lc(url, new_chapters[-1])
                continue

            LOGGER(__name__).info(f"[{ps}] Updates for {url}: {new_chapters}")
            await asyncio.sleep(5)

            for sub_data in subs_data[url]:
                (
                    chat,
                    title,
                    send_updates,
                    file_mode,
                    custom_filename,
                    custom_caption,
                    custom_thumb,
                ) = sub_data

                for ch_url in new_chapters:
                    ch = zeroint(ch_from_url(ch_url))
                    _ch = ch
                    if _is_numeric(ch):
                        _ch = f"Chapter {ch}"
                        ch = f"Ch - {ch}"

                    filename = custom_filename.format(ch=ch, manga=title)
                    caption = custom_caption.format(ch=ch, manga=title)
                    thumb = None

                    if custom_thumb:
                        thumb = (await AioHttp.download(custom_thumb))[0]

                    chapter_file = None
                    try:
                        if ps == "Manganato":
                            manga_id = url.split("/")[-1]
                            manga = await IManga(manga_id)._parse_info()

                            if not thumb:
                                thumb = (await AioHttp.download(manga.poster_url))[0]

                            chapter_file = await IManga.dl_chapter(
                                ch_url, filename, file_mode
                            )

                        elif ps == "Mangabuddy":
                            chapter_file = await IManga.dl_chapter(
                                ch_url, filename, file_mode
                            )

                        else:
                            filename += " @Adult_Mangas"
                            chapter_file = await PS.dl_chapter(
                                ch_url, filename, file_mode, **iargs(PS.iargs(ps))
                            )

                    except Exception:
                        if thumb:
                            os.remove(thumb)

                        LOGGER(__name__).exception(
                            f"Couldn't make chapter file for {ch_url}."
                        )
                        break

                    files = []
                    if isinstance(chapter_file, list):
                        for cf in chapter_file:
                            files.append(InputMediaDocument(cf, thumb=thumb))
                    else:
                        files.append(InputMediaDocument(chapter_file, thumb=thumb))

                    files[-1].caption = caption
                    try:
                        await bot.send_media_group(
                            chat, files, protect_content=ps in ("Manhwa18", "Toonily")
                        )
                    except Exception as e:
                        LOGGER(__name__).info(
                            f"Was unable to send new chapters to {chat}: {e}\n Removing the subscription for this chat."
                        )
                        await pdB.rm_sub(ps, url, chat)
                        await pdB.add_lc(url, new_chapters[-1])
                        break

                    for file in files:
                        os.remove(file.media)

                    if thumb:
                        os.remove(thumb)

                    if str(chat).startswith("-100") and send_updates:
                        chat_link = await get_chat_invite_link(chat)
                        reply_markup = None
                        if chat_link:
                            button = [InlineKeyboardButton("Read Here", url=chat_link)]
                            reply_markup = InlineKeyboardMarkup([button])

                        update_logs_chat = (
                            -1001848617769
                            if ps not in ["Manganato", "Mangabuddy"]
                            else -1001835330873
                        )

                        try:
                            await bot.send_message(
                                update_logs_chat,
                                CHAPTER_LOG_MSG.format(title=title, ch=_ch),
                                reply_markup=reply_markup,
                            )
                        except BaseException:
                            pass

                    await pdB.add_lc(url, ch_url)
                    await asyncio.sleep(3)


async def _updater():
    while True:
        wait_time = 5 * 60
        try:
            start = datetime.now()
            await update_subs()
            elapsed = datetime.now() - start
            wait_time = max((timedelta(seconds=wait_time) - elapsed).total_seconds(), 0)
            LOGGER(__name__).info(
                f"Time elapsed updating manhwas: {elapsed}, waiting for {wait_time}"
            )
        except BaseException as e:
            LOGGER(__name__).info(
                f"Got Error While Updating Manhwa: {e}", exc_info=True
            )
        if wait_time:
            await asyncio.sleep(wait_time)


asyncio.get_event_loop().create_task(_updater())


def _is_numeric(inp: str):
    try:
        try:
            int(inp)
        except ValueError:
            float(inp)
        return True
    except ValueError:
        return False
