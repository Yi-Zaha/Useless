import os
import re

from pyrogram import filters

from bot import bot, SUDOS
from bot.helpers.manga import PS
from bot.helpers.psutils import (
    ch_from_url,
    iargs,
    ps_link,
    zeroint,
)
from bot.utils.functions import (
    get_chat_link_from_msg,
    is_numeric,
)
from bot.utils.pdf import merge_pdfs


@bot.on_message(
    filters.regex(
        "^/read( -thumb)?( -fpdf)? (-h|-mc|-mh|-ws|-m|-18|-t6|-t|-20|-3z) (.*)"
    )
    & filters.user(SUDOS)
)
async def readp_handler(client, message):
    status = await message.reply("Processing...")
    is_thumb = bool(message.matches[0].group(1))
    site = message.matches[0].group(3).strip()
    input_str = message.matches[0].group(4)
    splited = input_str.split(" | ")

    if not input_str or len(splited) < 2:
        return await status.edit(
            "<b>Sorry, invalid syntax.</b>\n\nPlease provide the manga name and chapter number in the format: <code>/read -&lt;site&gt; &lt;manga_name&gt; | &lt;chapter_number&gt;</code>"
        )

    name, chapter = map(str.strip, splited[:2])

    try:
        link = await ps_link(site, name, chapter)
        args = iargs(site)
        pdfname = f"""Ch - {chapter.replace("-", ".")} {name.title().replace("'S", "'s").replace("’S", "'s")} @Adult_Mangas"""
        file = await PS.dl_chapter(link, pdfname, "pdf", **args)
        thumb = "thumb.jpg" if is_thumb else None
        await bot.send_document(message.chat.id, file, thumb=thumb)
        os.remove(file)
        await status.edit(f"<b>Successfully uploaded</b> [{name.title()}]({link})")
    except Exception as e:
        await status.edit(
            f"<b>Oops! Something went wrong.</b>\n\n<code>{type(e).__name__}: {e}</code>"
        )


@bot.on_message(filters.command("bulkp") & filters.user(SUDOS))
async def bulkp_handler(client, message):
    status = await message.reply("Processing...")
    if len(message.command) < 2:
        return await status.edit(
            "Invalid syntax. Please provide the site name and manga title."
        )

    reply = message.reply_to_message
    text = message.text.split(" ", 1)[1]
    site = text.split(" ")[0]
    merge_limit = re.search(r"-merge\D*(\d+)", text)
    if merge_limit:
        text = text.replace(merge_limit.group(), "").strip()
        merge_limit = int(merge_limit.group(1))
    pdf_pass = re.search(r"-pass (\S+)", text)
    if pdf_pass:
        text = text.replace(pdf_pass.group(), "").strip()
        pdf_pass = pdf_pass.group(1)
    flags = ("-thumb", "-protect", "-showpass", "-t", "-18")

    if reply and reply.photo:
        thumb = await reply.download()
    elif flags[0] in text:
        thumb = "thumb.jpg"
    else:
        thumb = None

    protect_content = flags[1] in text
    showpass = flags[2] in text
    for flag in flags:
        text = text.replace(flag, "", 1).strip()

    chat_id = message.chat.id
    if "|" in text:
        try:
            chat_id = int(text.split("|")[-1].strip())
        except ValueError:
            return await status.edit("Invalid Chat ID provided.")
        text = text.replace("|", "").replace(str(chat_id), "").strip()
    
    chat_link = None
    try:
        if text.startswith("https://"):
            url = text
            title = await PS.get_title(url)
        else:
            title = text
            url = await ps_link(site, title)

        title = title.replace("’", "'").replace("'S", "'s")
        ps = PS.guess_ps(url)
        cache_dir = f"cache/{ps}"
        if not os.path.isdir(cache_dir):
            os.makedirs(cache_dir)

        chapters = list(reversed([ch_link async for ch_link in PS.iter_chapters(url)]))
        pdf_batch = {}
        upload_msg, process_started = None, False
        for ch_link in chapters:
            chapter = zeroint(ch_from_url(ch_link))
            pdfname = (
                f"{cache_dir}/Ch - {chapter} {title} @Adult_Mangas"
                if is_numeric(chapter)
                else f"{cache_dir}/{chapter} {title} @Adult_Mangas"
            )
            chapter_file = await PS.dl_chapter(ch_link, pdfname, "pdf", **iargs(site), file_pass=pdf_pass if not merge_limit or ch_link == chapters[-1] else None)
            if not merge_limit:
                upload_msg = await bot.send_document(
                    chat_id,
                    chapter_file,
                    caption=f"<b>Password:</b> <code>{pdf_pass}</code>" if pdf_file and showpass else None,
                    thumb=thumb,
                    protect_content=protect_content,
                )
                os.remove(chapter_file)
            else:
                pdf_batch[chapter] = chapter_file
                if (
                    len(pdf_batch) == merge_limit
                    or ch_link == chapters[-1]
                ):
                    if len(pdf_batch) == 1:
                        upload_msg = await bot.send_document(
                            chat_id,
                            chapter_file,
                            caption=f"<b>Password:</b> <code>{pdf_pass}</code>" if pdf_file and showpass else None,
                            thumb=thumb,
                             protect_content=protect_content,
                        )
                        os.remove(chapter_file)
                        continue
                    start, *_, end = pdf_batch.keys()
                    pdfname = f"Ch [{start} - {end}] {title} @Adult_Mangas.pdf"
                    merged_file = merge_pdfs(pdfname, pdf_batch.values(), pdf_pass)
                    upload_msg = await bot.send_document(
                        chat_id,
                        merged_file,
                        caption=f"<b>Password:</b> <code>{pdf_pass}</code>" if pdf_file and showpass else None,
                        thumb=thumb,
                        protect_content=protect_content,
                    )
                    os.remove(merged_file)
                    [os.remove(pdf) for pdf in pdf_batch.values()]
                    pdf_batch.clear()

            if not process_started and upload_msg:
                chat_link = await get_chat_link_from_msg(upload_msg)
                await status.edit(
                    f"<code>Uploading all chapters...</code>\n\n<b>• Pornhwa:</b> [{title}]({url})\n<b>• Website:</b> <code>{ps}</code>\n<b>• Chat:</b> [Click Here]({chat_link})",
                    disable_web_page_preview=True,
                )
                process_started = True

        await status.edit(
            f"<code>Bulk Upload Finished!</code>\n\n<b>• Pornhwa:</b> [{title}]({url})\n<b>• Website:</b> <code>{ps}</code>\n<b>• Chat:</b> [Click Here]({chat_link})",
            disable_web_page_preview=True,
        )

        if thumb and thumb != "thumb.jpg":
            os.remove(thumb)

    except Exception as e:
        await status.edit(
            f"<b>Oops! Something went wrong.</b>\n\n<code>{type(e).__name__}: {e}</code>"
        )
