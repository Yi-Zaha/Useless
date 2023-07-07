import os
from pyrogram import filters
from bot import ALLOWED_USERS, bot
from bot.helpers.manga import PS
from bot.helpers.psutils import ch_from_url, iargs, ps_link, zeroint
from bot.utils.functions import get_chat_link_from_msg

@bot.on_message(
    filters.regex("^/read( -thumb)?( -fpdf)? (-h|-mc|-mh|-ws|-m|-18|-t6|-t|-20|-3z) (.*)")
    & filters.user(ALLOWED_USERS)
)
async def readp_handler(client, message):
    status = await message.reply("Processing...")
    is_thumb = bool(message.matches[0].group(1))
    bool(message.matches[0].group(2))
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


@bot.on_message(filters.command("bulkp") & filters.user(ALLOWED_USERS))
async def bulkp_handler(client, message):
    status = await message.reply("Processing...")
    if len(message.command) < 2:
        return await status.edit("Invalid syntax. Please provide the site name and manga title.")
    
    reply = message.reply_to_message
    text = message.text.split(" ", 1)[1]
    site = text.split(" ")[0]
    flags = ("-thumb", "-protect", "-t", "-18")

    if reply and reply.photo:
        thumb = await reply.download()
    elif flags[0] in text:
        thumb = "thumb.jpg"
    else:
        thumb = None
    
    protect_content = flags[1] in text
    for flag in flags:
        text = text.replace(flag, "", 1).strip()

    chat_id = message.chat.id
    if "|" in text:
        try:
            chat_id = int(text.split("|")[-1].strip())
        except ValueError:
            return await status.edit("Invalid Chat ID provided.")
        text = text.replace("|", "").replace(str(chat_id), "").strip()

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

        chapters = []
        async for ch_link in PS.iter_chapters(url):
            chapters.append(ch_link)
        chapters.reverse()

        process_started = False
        for ch_link in chapters:
            chapter = zeroint(ch_from_url(ch_link))
            pdfname = f"{cache_dir}/Ch - {chapter} {title} @Adult_Mangas"
            chapter_file = await PS.dl_chapter(ch_link, pdfname, "pdf", **iargs(site))
            upload_msg = await bot.send_document(
                chat_id, chapter_file, thumb=thumb, protect_content=protect_content
            )
            os.remove(chapter_file)

            if not process_started:
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