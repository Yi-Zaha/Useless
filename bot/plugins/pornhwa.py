import asyncio
import os
import re

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import SUDOS, bot
from bot.helpers.manga import PS
from bot.helpers.psutils import ch_from_url, iargs, ps_link, zeroint
from bot.logger import LOGGER
from bot.utils import BULK_PROCESS
from bot.utils.functions import (
    get_chat_link,
    get_random_id,
    is_numeric,
    remove_files,
    split_list,
)
from bot.utils.pdf import merge_pdfs


@Client.on_message(
    filters.regex(
        "^/read( -thumb)? (-h|-mc|-mh|-ws|-m|-18|-t6|-t|-20|-3z|-md|-m18c) (.*)"
    )
    & filters.user(SUDOS)
)
async def readp_handler(client, message):
    status = await message.reply("Processing...")
    is_thumb = bool(message.matches[0].group(1))
    site = message.matches[0].group(2).strip()
    input_str = message.matches[0].group(3)
    splited = input_str.split(" | ")

    if not input_str or len(splited) < 2:
        return await status.edit(
            "<b>Sorry, invalid syntax.</b>\n\nPlease provide the manga name and chapter number in the format: <code>/read -&lt;site&gt; &lt;manga_name&gt; | &lt;chapter_number&gt;</code>"
        )

    if len(splited) >= 3:
        link, name, chapter = map(str.strip, splited[:3])
    elif len(splited) == 2:
        name, chapter = map(str.strip, splited[:2])
        link = None

    try:
        link = link or await ps_link(site, name, chapter)
        args = iargs(site)
        pdfname = f"""Ch - {chapter.replace("-", ".")} {name} @PornhwaCollection"""
        try:
            file = await PS.dl_chapter(link, pdfname, "pdf", **args)
        except ValueError:
            if site == "-h":
                link = await ps_link(site, name, chapter, chapter_suffix=False)
                file = await PS.dl_chapter(link, pdfname, "pdf", **args)
            else:
                raise
        thumb = "thumb.jpg" if is_thumb else "bot/resources/phub_files_thumb.png"
        await bot.send_document(message.chat.id, file, thumb=thumb)
        asyncio.create_task(remove_files(file))
        await status.edit(f"<b>Successfully uploaded</b> [{name.title()}]({link})")
    except Exception as e:
        await status.edit(
            f"<b>Oops! Something went wrong.</b>\n\n<code>{type(e).__name__}: {e}</code>"
        )


@Client.on_message(filters.command("pbulk") & filters.user(SUDOS))
async def bulkp_handler(client, message):
    if len(message.command) < 2:
        return await message.reply(
            "Invalid syntax. Please provide the site name and manga title."
        )

    status = await message.reply("Processing...")

    text = message.text.split(" ", 1)[1]
    ps_site = PS.iargs(text.split(" ")[0])  # To Check
    if ps_site:
        text = text.replace(text.split(" ")[0], "", 1)
    merge_limit = re.search(r"-merge.(\d+)", text)
    if merge_limit:
        text = text.replace(merge_limit.group(), "")
        merge_limit = int(merge_limit[1])
    pdf_pass = re.search(r"-pass.(\S+)", text)
    if pdf_pass:
        text = text.replace(pdf_pass.group(), "")
        pdf_pass = pdf_pass[1]
    start_from = re.search(r"-start.(\S+)", text)
    if start_from:
        text = text.replace(start_from.group(), "")
        start_from = start_from[1]
    end_to = re.search(r"-end.(\S+)", text)
    if end_to:
        text = text.replace(end_to.group(), "")
        end_to = end_to[1]

    reply = message.reply_to_message
    flags = ("-thumb", "-protect", "-showpass", "-comick_vol")
    if reply and reply.photo:
        thumb = await reply.download("cache/")
    elif flags[0] in text:
        thumb = "thumb.jpg"
    else:
        thumb = "bot/resources/phub_files_thumb.png"
    *_, protect_content, showpass, comick_vol = (flag in text for flag in flags)
    for flag in flags:
        text = text.replace(flag, "", 1).strip()

    chat_id = message.chat.id
    if "|" in text:
        splited = text.split("|")
        if len(splited) >= 3:
            link, name, chat_id = map(str.strip, splited[:3])
        elif len(splited) == 2:
            link_or_name, chat_or_name = map(str.strip, splited)
            if link_or_name.startswith("https://"):
                link, name = link_or_name, None
            else:
                name, link = link_or_name, None
            if chat_or_name[1:].isdigit():
                chat_id = chat_or_name
            else:
                name = chat_or_name
        else:
            await status.edit("Invalid Syntax. Please provide input properly!")
            return
        try:
            chat_id = int(chat_id)
        except ValueError:
            return await status.edit("Chat ID should be an integer!")
    elif text.startswith("https://"):
        link, name = text, None
    else:
        name, link = text, None

    rid = get_random_id()
    bulk_id = f"cancel_bulk:{message.from_user.id}:{rid}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", bulk_id)]])

    try:
        await process_bulk(
            link,
            chat_id,
            name,
            ps_site,
            merge_limit,
            pdf_pass,
            start_from,
            end_to,
            thumb,
            protect_content,
            showpass,
            bulk_id,
            markup,
            status,
            comick_vol,
        )
    except Exception as e:
        await status.edit(
            f"<b>Oops! Something went wrong.</b>\n\n<code>{type(e).__name__}: {e}</code>"
        )
        LOGGER(__name__).exception(e)
    finally:
        if bulk_id in BULK_PROCESS:
            BULK_PROCESS.remove(bulk_id)


async def process_bulk(
    link,
    chat_id,
    name=None,
    ps_site=None,
    merge_limit=None,
    pdf_pass=None,
    start_from=None,
    end_to=None,
    thumb=None,
    protect_content=None,
    showpass=None,
    bulk_id=None,
    markup=None,
    status=None,
    status_text=None,
    comick_vol=None,
):
    if not link:
        if ps_site:
            link = await ps_link(PS.iargs(ps_site), name)
        else:
            if status:
                await status.edit("Invalid Syntax. Please provide input properly!")
            return

    ps = PS.guess_ps(link)
    ps_site = PS.iargs(ps)
    title = name or await PS.get_title(link)
    chapters = [
        chapter async for chapter in PS.iter_chapters(link, comick_vol=comick_vol)
    ]
    chapters.reverse()
    start_index = (
        next((n for n, chapter in enumerate(chapters) if chapter[1] == start_from), 0)
        if start_from
        else 0
    )
    end_index = (
        next(
            (n for n, chapter in enumerate(chapters, 1) if chapter[1] == end_to),
            len(chapters),
        )
        if end_to
        else len(chapters)
    )
    chapters = chapters[start_index:end_index]

    files_count = (
        len(split_list(chapters, merge_limit)) if merge_limit else len(chapters)
    )
    files_uploaded = 0
    if files_count == 0:
        if status:
            await status.edit("No chapters found to bulk.")
        return

    chat_link = await get_chat_link(chat=chat_id)

    cache_dir = os.path.join("cache/", ps)
    os.makedirs(cache_dir, exist_ok=True)

    filename_format = "{chapter} {manga} @PornhwaCollection"

    pdf_batch = {}
    upload_msg, chapter_file = None, None
    if bulk_id:
        BULK_PROCESS.add(bulk_id)
        if not markup:
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", bulk_id)]])

    if status_text:
        status_text += "\n\n"
    upload_chs = []
    for ch, ch_link in chapters:
        if bulk_id and bulk_id not in BULK_PROCESS:
            if status:
                await status.edit("Cancelled by User.")
            asyncio.create_task(remove_files(pdf_batch.values()))
            asyncio.create_task(remove_files(chapter_file))
            return
        chapter = ch or zeroint(ch_from_url(ch_link))
        if is_numeric(chapter):
            upload_chs.append(chapter)
            file_name = filename_format.format(chapter=f"Ch - {chapter}", manga=title)
        else:
            file_name = filename_format.format(chapter=chapter, manga=title)
        file_path = os.path.join(cache_dir, file_name)
        chapter_file = await PS.dl_chapter(
            ch_link,
            file_path,
            "pdf",
            file_pass=(
                pdf_pass
                if (not merge_limit) or (ch_link == chapters[-1][1] and not pdf_batch)
                else None
            ),
            **iargs(ps_site),
        )
        caption = (
            f"<b>Password:</b> <code>{pdf_pass}</code>"
            if pdf_pass and showpass
            else None
        )
        if not merge_limit:
            upload_msg = await bot.send_document(
                chat_id,
                chapter_file,
                caption=caption,
                thumb=thumb,
                protect_content=protect_content,
            )
            asyncio.create_task(remove_files(chapter_file))
            files_uploaded += 1
        else:
            pdf_batch[chapter] = chapter_file
            if len(pdf_batch) == merge_limit or ch_link == chapters[-1][1]:
                if len(pdf_batch) == 1:
                    upload_msg = await bot.send_document(
                        chat_id,
                        chapter_file,
                        caption=caption,
                        thumb=thumb,
                        protect_content=protect_content,
                    )

                    asyncio.create_task(remove_files(chapter_file))
                else:
                    start, *_, end = pdf_batch.keys()
                    caption = f"<i>Ch [{start} - {end}]</i>"
                    if showpass and pdf_pass:
                        caption += f"\n<b>Password:</b> <code>{pdf_pass}</code>"
                    pdfname = f'{filename_format.format(chapter=f"Ch [{start} - {end}]", manga=title)}.pdf'
                    merged_file = await merge_pdfs(
                        pdfname, pdf_batch.values(), password=pdf_pass
                    )
                    upload_msg = await bot.send_document(
                        chat_id,
                        merged_file,
                        caption=caption,
                        thumb=thumb,
                        protect_content=protect_content,
                    )
                    asyncio.create_task(remove_files(merged_file))
                    asyncio.create_task(remove_files(list(pdf_batch.values())))
                    pdf_batch.clear()
                files_uploaded += 1

        try:
            if status:
                status = await status.edit(
                    (
                        f"{status_text if status_text else ''}"
                        f"**Uploading Manga from - {ps}**...\n\n"
                        f"**››Manga:** [{title}]({link})\n"
                        f"**››Location:** [Here]({chat_link})\n"
                        f"**››Progress:** `{files_uploaded}`/`{files_count}` files uploaded."
                    ),
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
        except BaseException:
            pass

    if status:
        status = await status.edit(
            (
                f"{status_text if status_text else ''}"
                f"**Uploaded Manga from - {ps}.**\n\n"
                f"**››Manga:** [{title}]({link})\n"
                f"**››Location:** [Here]({chat_link})\n"
                f"**››Progress:** `{files_uploaded}`/`{files_count}` files uploaded."
            ),
            disable_web_page_preview=True,
        )

    if thumb and not thumb.endswith(("thumb.jpg", "phub_files_thumb.png")):
        asyncio.create_task(remove_files(thumb))

    return upload_chs[-1], status
