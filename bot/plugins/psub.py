import asyncio
import io
import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlparse

from pyrogram import Client, errors, filters
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
from bot.utils.db import dB, pdB
from bot.utils.functions import (
    ask_message,
    file_to_graph,
    get_chat_invite_link,
    is_numeric,
    is_url,
)

PH_LOG_CHAT = -1001848617769
DISABLED_PS = []
DELAYED_PS = {"Manhwa18": 10 * 60, "Comick": 3 * 60 * 60}
CHAPTER_LOG_MSG = """
<i><b>#New_Chapter</b></i>
<i>→{title}
→{ch}</i>
"""
CHAPTER_FILE_NAME_PATTERN = re.compile(
    "(?P<chapter>\\d+(\\.\\d+)?)[\\s\\d+._-]+(?P<title>[^\\d@]+)[ ._](?=@)?"
)


@Client.on_message(
    filters.command("msub") & filters.user(ALLOWED_USERS) & filters.private
)
async def add_sub(client, message):
    req, res = await ask_message(message, "Provide the manga URL")
    url = res.text.strip()

    try:
        ps = PS.guess_ps(url)
    except ValueError:
        return await res.reply("Invalid URL.")

    req, res = await ask_message(
        res, "Provide the manga's title.\n\n/skip to set to default."
    )
    title = None if res.text.lower().split(" ")[0] in ("/skip") else res.text.strip()
    status = await res.reply("Processing...")
    try:
        title = title or await PS.get_title(url, ps=ps)
        lc = await pdB.get_lc(url)
        if not lc:
            agen = PS.iter_chapters(url, ps=ps)
            last_chapter = (await anext(agen))[1]
            await pdB.add_lc(url, last_chapter)
        else:
            last_chapter = lc["lc_url"]
    except Exception as e:
        return await status.edit(
            f"Oops, something went wrong!\n\n<code>{e.__class__.__name__}: {e}</code>"
        )
    await status.delete()

    req, res = await ask_message(res, "Provide the chat ID.")
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

    req, res = await ask_message(
        res,
        "Tell me the mode of the file in which you want to receive updates.\n\n"
        "Choose between:\n"
        "- <code>PDF</code>\n"
        "- <code>CBZ</code>\n"
        "- <code>BOTH</code>\n\n",
    )
    file_mode = res.text.lower()
    if all(fm not in file_mode for fm in ("graph", "pdf", "cbz", "both")):
        return await res.reply("Invalid file mode.")

    req, res = await ask_message(
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

    req, res = await ask_message(
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

    req, res = await ask_message(
        res,
        "Provide the thumbnail for chapter files.\n\n"
        "<i>/skip to skip this part.</i>",
        filters=(filters.text | filters.photo),
    )
    if res.text and res.text.lower().split(" ")[0] in ["/skip"]:
        thumb_url = None
    elif res.photo:
        tmp_file = await res.download()
        thumb_url = await file_to_graph(tmp_file)
        os.remove(tmp_file)
    else:
        thumb_url = res.text

    req, res = await ask_message(
        res, "Provide any password you want to set for files.\n\n/skip to set None."
    )
    if res.text.lower().split(" ")[0] in ("/skip"):
        file_pass = None
    else:
        file_pass = res.text.strip()

    req, res = await ask_message(
        res,
        "Would you like this subscription to have update notifs? Give chat_id separated by one line below if you want to make a custom notifs chat.\n\n"
        "<i>Answer in Yes or No.</i>",
    )
    if len(res.text.splitlines()) == 1:
        send_updates = res.text.lower() in ("yes", "true")
        notifs_chat = None
    else:
        send_updates = res.text.splitlines()[0].lower() in ("yes", "true")
        notifs_chat = res.text.splitlines()[1]
        if not notifs_chat[1:].isdigit():
            return await res.reply("Chat ID should be an integer!")
        notifs_chat = int(notifs_chat)

    await pdB.add_sub(
        ps,
        url,
        chat,
        title,
        send_updates=send_updates,
        notifs_chat=notifs_chat,
        file_mode=file_mode.upper(),
        custom_filename=custom_filename,
        custom_caption=custom_caption,
        thumb_url=thumb_url,
        file_pass=file_pass,
    )

    text = "**Added New Subscription**\n\n"
    text += f"**›› Url →** `{url}`\n"
    text += f"**›› Chat →** `{chat}`\n"
    text += f"**›› File Mode →** `{file_mode.upper()}`\n"

    if custom_filename:
        text += f"**›› Custom Filename →** `{custom_filename}`\n"
    if custom_caption:
        text += f"**›› Custom Caption →** `{custom_caption}`\n"
    if thumb_url:
        text += f"**›› Custom Thumb →** `{thumb_url}`\n"
    if file_pass:
        text += f"**›› File Password →** `{file_pass}`\n" if file_pass else ""
    if notifs_chat:
        text += f"**›› Notification Chat →** `{notifs_chat}`"

    await message.reply(text, parse_mode=ParseMode.MARKDOWN)


@Client.on_message(
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


@Client.on_message(
    filters.command("subs") & filters.user(ALLOWED_USERS) & filters.private
)
async def list_all_subs(client, message):
    subs = {}
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
        text = f"<b>Total Subs:</b> <code>{subs_count}</code>\n\n{text}"
        await message.reply(text)


@Client.on_message(filters.command("newch") & filters.user(ALLOWED_USERS))
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

    if is_numeric(ch):
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


async def get_new_updates():
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
                async for chapter in PS.iter_chapters(url):
                    if chapter[1] == last_chapter or len(new_chapters) > 30:
                        break
                    if ps == "Comick":
                        last_ch = dict(parse_qsl(urlparse(last_chapter).query)).get(
                            "ch"
                        )
                        if not is_numeric(str(chapter[0])) or not is_numeric(
                            str(last_ch)
                        ):
                            new_chapters.append(chapter)
                        elif float(chapter[0]) > float(last_ch):
                            new_chapters.append(chapter)
                    else:
                        new_chapters.append(chapter)

                if new_chapters:
                    new_chapters.reverse()
                    all_updates[ps][url] = new_chapters

    return all_updates


async def update_subs(get_updates=get_new_updates, to_sleep=True):
    LOGGER(__name__).info("Updating PS Subs...")
    subs = {}
    async for sub in pdB.all_subs():
        url = sub["url"]
        if url not in subs:
            subs[url] = []
        subs[url].append(sub)

    for ps, updates in (await get_updates()).items():
        if updates and ps in DELAYED_PS and to_sleep:
            delay_time = DELAYED_PS[ps]
            timestamp = DELAYED_PS.setdefault(f"{ps}_ts", time.time())
            if int(time.time() - timestamp) < delay_time:
                continue
            DELAYED_PS.pop(f"{ps}_ts")

        LOGGER(__name__).info(f"Checking for PS: {ps}")

        for url, new_chapters in updates.items():
            if url not in subs:
                await pdB.add_lc(url, new_chapters[-1][1])
                continue

            LOGGER(__name__).info(
                f"[{ps}] Updates for {url}: {[ch_link for _, ch_link in new_chapters]}"
            )
            await asyncio.sleep(5)

            for sub in subs[url]:
                chat = sub["chat"]
                title = sub["title"]
                send_updates = sub.get("send_updates") or False
                file_mode = sub.get("file_mode") or "pdf"
                custom_filename = sub.get("custom_filename") or "{ch} {manga}"
                custom_caption = sub.get("custom_caption") or ""
                custom_thumb = sub.get("custom_thumb") or False
                file_pass = sub.get("file_pass", None)
                notifs_chat = sub.get("notifs_chat", 0)
                ch_nos = []
                for ch, ch_url in new_chapters:
                    ch = ch or zeroint(ch_from_url(ch_url))
                    _ch = ch
                    ch_no = None
                    if is_numeric(ch):
                        ch_no = ch
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
                            if not thumb:
                                manga_id = url.split("/")[-1]
                                manga = await IManga(manga_id)._parse_info()
                                thumb = (await AioHttp.download(manga.poster_url))[0]

                            chapter_file = await IManga.dl_chapter(
                                ch_url, filename, file_mode, file_pass=file_pass
                            )

                        elif ps in ["Mangabuddy", "Comick"]:
                            chapter_file = await IManga.dl_chapter(
                                ch_url, filename, file_mode, file_pass=file_pass
                            )

                        else:
                            thumb = "bot/resources/phub_files_thumb.png"
                            if not os.path.exists(thumb):
                                await AioHttp.download(
                                    "https://graph.org//file/bc03ef186c2c19287adbb.jpg",
                                    filename=thumb,
                                )
                            filename = f"{ch} {title} @PornhwaCollection"
                            chapter_file = await PS.dl_chapter(
                                ch_url,
                                filename,
                                file_mode,
                                file_pass=file_pass,
                                **iargs(PS.iargs(ps)),
                            )

                    except Exception as e:
                        if thumb and not thumb.endswith("phub_files_thumb.png"):
                            os.remove(thumb)

                        LOGGER(__name__).error(
                            f"Couldn't make chapter file for {ch_url} → {e.__class__.__name__}: {e}"
                        )
                        break

                    read_url = None
                    files = []
                    if isinstance(chapter_file, list):
                        for cf in chapter_file:
                            if is_url(str(cf)):
                                read_url = cf
                                continue
                            files.append(InputMediaDocument(cf, thumb=thumb))
                    elif is_url(str(chapter_file)):
                        read_url = chapter_file
                    else:
                        files.append(InputMediaDocument(chapter_file, thumb=thumb))

                    if files:
                        files[-1].caption = caption
                        try:
                            msg = await bot.send_media_group(
                                chat,
                                files,
                                protect_content=ps in PS.__all__[:4],
                            )
                            ch_nos.append(ch_no)
                        except (
                            errors.PeerIdInvalid,
                            errors.UserIsBlocked,
                            errors.ChatWriteForbidden,
                        ) as e:
                            LOGGER(__name__).info(
                                f"Was unable to send new chapters to {chat}: {e}... removing the subscription for this chat."
                            )
                            await pdB.rm_sub(ps, url, chat)
                            break
                        except Exception as e:
                            LOGGER(__name__).info(
                                f"Was unable to send new chapters to {chat}: {e}"
                            )
                            break

                        for file in files:
                            os.remove(file.media)
                    else:
                        reply_markup = None
                        if read_url:
                            reply_markup = InlineKeyboardMarkup(
                                [[InlineKeyboardButton("Read Online", url=read_url)]]
                            )
                        try:
                            await bot.send_message(
                                chat, f"{title} - {_ch}", reply_markup=reply_markup
                            )
                            ch_nos.append(ch_no)
                        except (
                            errors.PeerIdInvalid,
                            errors.UserIsBlocked,
                            errors.ChatWriteForbidden,
                        ) as e:
                            LOGGER(__name__).info(
                                f"Was unable to send new chapters to {chat}: {e}... removing the subscription for this chat."
                            )
                            await pdB.rm_sub(ps, url, chat)
                            break
                        except Exception as e:
                            LOGGER(__name__).info(
                                f"Was unable to send new chapters to {chat}: {e}"
                            )
                            break

                    if thumb and not thumb.endswith("phub_files_thumb.png"):
                        os.remove(thumb)

                    if str(chat).startswith("-100") and send_updates:
                        chat_link = await get_chat_invite_link(chat)
                        buttons = []
                        reply_markup = None
                        if chat_link:
                            buttons.append(
                                [InlineKeyboardButton("Read Here", url=chat_link)]
                            )
                        if read_url and files:
                            buttons.append(
                                [InlineKeyboardButton("Read Online", url=read_url)]
                            )
                        if buttons:
                            reply_markup = InlineKeyboardMarkup(buttons)

                        update_logs_chat = notifs_chat or (
                            -1001848617769 if ps in PS.__all__[:4] else -1001835330873
                        )

                        try:
                            await bot.send_message(
                                update_logs_chat,
                                CHAPTER_LOG_MSG.format(title=title, ch=_ch),
                                reply_markup=reply_markup,
                            )
                        except Exception as e:
                            LOGGER(__name__).info(
                                f"Error while sending new notifs to {update_logs_chat}: {e}"
                            )

                    await pdB.add_lc(url, ch_url)
                    await asyncio.sleep(3)
                if ch_nos:
                    await dB.update_one(
                        {"PHUB_POST_DB.posts.fchannel.chat_id": chat},
                        {"$set": {"PHUB_POST_DB.posts.$.chapters": f"{ch_nos[-1]}"}},
                    )


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
