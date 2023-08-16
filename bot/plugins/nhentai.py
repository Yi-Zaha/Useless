import asyncio
import os
import re

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.errors import ChannelInvalid, PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import ALLOWED_USERS, CACHE_CHAT, bot
from bot.config import Config
from bot.helpers.manga import Nhentai
from bot.logger import LOGGER
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.functions import b64_encode, generate_share_url, images_to_graph

NH_CHANNEL = Config.get("NH_CHANNEL", -1001867670372)
NH_CHAT = Config.get("NH_CHAT", -1001666665549)
DL_LOCK = asyncio.Lock()
BULK_PROCESS = []


async def generate_doujin_info(doujin, graph=False):
    if graph:
        graph_link = await images_to_graph(
            f"{doujin.english_title} | @Nhentai_Doujins",
            doujin.image_urls,
            author="Nhentai Hub",
            author_url="https://telegram.me/Nhentai_Doujins",
        )
        doujin.read_url = graph_link or doujin.url.rtrip("/") + "/1"

    msg = f"[{doujin.english_title}]({doujin.read_url)\n" f"\n➤ **Code:** [{doujin.code}]({doujin.url})"

    if doujin.categories:
        msg += f"\n➤ **Type:** {' '.join(doujin.categories)}"

    if doujin.parodies:
        msg += f"\n➤ **Parodies:** {' '.join(doujin.parodies)}"

    if doujin.artists:
        msg += f"\n➤ **Artists:** {' '.join(doujin.artists)}"

    if doujin.languages:
        msg += f"\n➤ **Languages:** {' '.join(doujin.languages)}"

    msg += f"\n➤ **Pages:** {doujin.pages}"

    if doujin.tags:
        msg += f"\n➤ **Tags:** {' '.join(doujin.tags)}"

    return msg


async def download_doujin_files(doujin, filename=None, mode="BOTH"):
    if not filename:
        filename = str(doujin.code)
    global DL_LOCK
    async with DL_LOCK:
        result = await doujin.dl_chapter(filename, mode)
        return result


@bot.on_message(filters.command("nh") & filters.user(ALLOWED_USERS))
async def nh_handler(client, message):
    if len(message.command) == 1:
        return await message.reply(
            "Please provide a doujin code to upload in the channel."
        )

    status = await message.reply("Processing... Please wait.")
    code = message.command[1]
    try:
        doujin = Nhentai(code)
        await doujin.get_data()
    except Exception:
        await status.edit("Doujin not found on nhentai.")
        return
    
    doujin_info = await generate_doujin_info(doujin, graph=False)
    
    await status.edit(
        f"Processing... Generating details for [{doujin.english_title}]({doujin.url})"
    )
    
    graph_url, pdf, cbz = await download_doujin_files(
        doujin,
        filename=doujin.pretty_title.replace("/", "|").split("|")[0][:41].strip()
        + " @Nhentai_Doujins",
        mode="ALL",
    )
    if graph_url:
        doujin_info = doujin_info.replace(
            doujin_info.splitlines()[0], f"[{doujin.english_title}]({graph_url})",
        )

    await client.send_message(
        CACHE_CHAT, doujin_info, disable_web_page_preview=True
    )
    first_msg = await client.send_document(CACHE_CHAT, pdf, caption="**PDF VIEW**")
    last_msg = await client.send_document(CACHE_CHAT, cbz, caption="**CBZ VIEW**")

    url = generate_share_url("expiry", first_msg.id, last_msg.id)

    buttons = [[InlineKeyboardButton("⛩️ Read Here ⛩️", url=url)]]

    mess = await client.send_message(
        NH_CHANNEL,
        doujin_info,
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    await client.send_cached_media(NH_CHANNEL, "CAADAQADRwIAArtf8EeIGkF9Fv05gQI")
    here = f"[{mess.chat.title}]({mess.link})"
    await status.edit(
        f"<i>[{doujin.english_title}]({doujin.url}) has been uploaded in {here}.</i>"
    )
    os.remove(pdf)
    os.remove(cbz)


@bot.on_message(filters.command("nhentai"))
async def nhentai_handler(client, message):
    flags = ("-wt",)
    no_graph = flags[0] in message.text
    for flag in flags:
        for cmd in message.command[:-1]:
            if flag in cmd:
                message.command.remove(cmd)
    status = await message.reply("Processing... Please wait.")
    if len(message.command) == 1:
        return await status.edit("Please provide the doujin's code or URL.")
    code = message.command[1]
    try:
        doujin = Nhentai(code)
        await doujin.get_data()
    except Exception:
        await status.edit("Doujin not found on nhentai.")
        return

    doujin_info = await generate_doujin_info(doujin, graph=not no_graph)
    await status.edit(f"Processing... Downloading [{doujin.english_title}]({doujin.url})")

    pdf, cbz = await download_doujin_files(doujin)

    await client.send_message(
        message.chat.id, doujin_info, parse_mode=ParseMode.MARKDOWN
    )
    await asyncio.gather(
        client.send_document(message.chat.id, pdf),
        client.send_document(message.chat.id, cbz),
    )

    await status.delete()
    os.remove(pdf)
    os.remove(cbz)


@bot.on_message(filters.command("dn"))
async def telegraph_nhentai(client, message):
    status = await message.reply("`Processing...`")
    if len(message.command) == 1:
        return await status.edit("Please provide the doujin's code or URL.")

    code = message.command[1]
    try:
        doujin = Nhentai(code)
        await doujin.get_data()
    except Exception:
        await status.edit("Doujin not found on nhentai.")
        return

    doujin_info = await generate_doujin_info(doujin, graph=True)
    await status.edit(f"Processing... [{doujin.english_title}]({doujin.url})")

    await status.edit(doujin_info, parse_mode=ParseMode.MARKDOWN)


@bot.on_message(filters.linked_channel & ~filters.sticker & filters.chat(NH_CHAT))
async def clean_nh_chat(client, message):
    if "➤ Tags:" in str(message.text):
        await message.delete()


@bot.on_message(filters.command("nhentai_bulk") & filters.user(ALLOWED_USERS))
async def doujins_nhentai(client, message):
    nh_match = re.search(r"https:\/\/nhentai\..+/", message.text)
    if len(message.command) == 1 or not nh_match:
        return await message.reply("Please provide the nhentai doujins Url.")
    flags = ("-en", "-wt", "-reverse")
    en, no_graph, to_reverse = (flag in message.text for flag in flags)
    for flag in flags:
        if flag in message.text:
            message.text = message.text.replace(flag, "", 1)

    text = message.text.split(" ", 1)[1]
    if "|" in text:
        try:
            url, chat = map(str.strip, text.split("|"))
            chat = int(chat)
        except ValueError:
            pass
    else:
        url = text
        chat = message.chat.id

    pid = f"nh_bulk:{b64_encode(f'{url}-{chat}')}"[:64]
    if pid in BULK_PROCESS:
        return await message.reply(
            "This link is already in process... Please wait for it to be completed!"
        )
    if pid not in BULK_PROCESS:
        BULK_PROCESS.append(pid)
    status = await message.reply("Processing... Please wait.")
    doujins = await Nhentai.doujins_from_url(url)
    doujins_count = len(doujins)

    if doujins_count == 0:
        return await status.edit("No doujins found from URL.")
    
    if to_reverse:
        doujins.reverse()

    cancel_button = [InlineKeyboardButton("Cancel", pid)]
    doujin_list_text = "\n".join(
        [f"→[{data['title']}]({data['url']})" for data in doujins]
    )
    status = await status.edit(
        f"<b>{doujins_count} doujins found</b>:\n{doujin_list_text}",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([cancel_button]),
    )

    success_count = 0
    error_count = 0

    for index, data in enumerate(doujins, start=1):
        if pid not in BULK_PROCESS:
            return await status.edit(
                f"{status.text.html}\n\n<b>Cancelled!</b>",
                disable_web_page_preview=True,
            )

        try:
            doujin = await Nhentai(code)
            await doujin.get_data()
            if en and "#english" not in doujin.languages:
                continue
            doujin_info = await generate_doujin_info(doujin, graph=not no_graph)
            pdf, cbz = await download_doujin_files(doujin)

            try:
                if no_graph:
                    await client.send_photo(
                        chat,
                        doujin.cover_url,
                        caption=doujin_info,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                else:
                    await client.send_message(
                        chat, doujin_info, parse_mode=ParseMode.MARKDOWN
                    )
                await asyncio.gather(
                    client.send_document(chat, pdf), client.send_document(chat, cbz)
                )
                success_count += 1
            finally:
                os.remove(pdf)
                os.remove(cbz)
        except (ChannelInvalid, PeerIdInvalid):
            if pid in BULK_PROCESS:
                BULK_PROCESS.remove(pid)
            return await status.edit(
                f"{status.text.html}\n\n<b>Invalid Chat Id Given.</b>",
                disable_web_page_preview=True,
            )
        except Exception as e:
            LOGGER(__name__).info(
                f"Error occurred while sending doujin no. {doujin.code}: {e}"
            )
            error_count += 1
        progress_text = f"**Uploaded:** {index}/{doujins_count}\n**Successful Uploads:** {success_count}\n**Errors:** {error_count}"
        await status.edit(
            f"{status.text.html}\n\n{progress_text}",
            disable_web_page_preview=True,
            reply_markup=status.reply_markup,
        )
    if en and success_count == 0 and error_count == 0:
        await status.edit(
            f"{status.text.html}\n\n<b>No English Doujin Found Here.</b>",
            disable_web_page_preview=True,
        )
    else:
        await status.edit_reply_markup(None)
    BULK_PROCESS.remove(pid)


@bot.on_callback_query(filters.regex(r"nh_bulk:.*"))
async def cancel_nh_bulk(client, callback):
    if callback.data not in BULK_PROCESS:
        return await callback.answer(
            "This process is not active anymore.", show_alert=True
        )
    BULK_PROCESS.remove(callback.data)
    await callback.answer("This process will be cancelled soon!", show_alert=True)
