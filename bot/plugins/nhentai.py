import asyncio

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import ALLOWED_USERS, CACHE_CHAT, LOG_CHAT, bot
from bot.config import Config
from bot.helpers.manga import Nhentai
from bot.helpers.nhentai_functions import (
    download_doujin_files,
    generate_doujin_info,
    generate_telegraph_link,
)
from bot.utils.functions import generate_share_url

NH_CHAT = Config.get("NH_CHAT", -1001867670372)


@bot.on_message(filters.command("nh") & filters.user(ALLOWED_USERS))
async def nh_handler(client, message):
    if len(message.command) == 1:
        return await message.reply(
            "Please provide a doujin code to upload in the channel."
        )

    status = await message.reply("Processing... Please wait.")
    code = message.command[1]
    try:
        doujin = await Nhentai().get(code)
    except Exception:
        await status.edit("Doujin not found on nhentai.")
        return

    doujin_info = generate_doujin_info(doujin)
    await status.edit(
        f"Processing... Generating details for [{doujin.title}]({doujin.url})"
    )

    pdf, cbz = await download_doujin_files(
        doujin,
        file=doujin.title.replace("/", "|").split("|")[0][:40].strip() + " @Nhentai_Doujins",
    )
    graph_link = await generate_telegraph_link(doujin)
    graph_link = graph_link or doujin.read_url
    graph_post = f"[{doujin.title}]({graph_link})"
    doujin_info = doujin_info.replace(doujin_info.split("\n")[0], graph_post)

    await client.send_message(LOG_CHAT, graph_link)
    await asyncio.sleep(3)

    await client.send_message(CACHE_CHAT, doujin_info, disable_web_page_preview=True)
    await client.send_document(CACHE_CHAT, pdf, caption="**PDF VIEW**")
    last_msg = await client.send_document(CACHE_CHAT, cbz, caption="**CBZ VIEW**")

    url = generate_share_url("expiry", message.chat.id, last_msg.id)

    buttons = [[InlineKeyboardButton("⛩️ Read Here ⛩️", url=url)]]
    mess = await client.send_message(
        NH_CHAT,
        doujin_info.replace(graph_post, f"[{doujin.title}]({url})"),
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    await client.send_cached_media(NH_CHAT, "CAADAQADRwIAArtf8EeIGkF9Fv05gQI")
    here = f"[{mess.chat.title}]({mess.link})"
    await status.edit(
        f"<i>[{doujin.title}]({doujin.url}) has been uploaded in {here}.</i>"
    )
    os.remove(pdf)
    os.remove(cbz)


@bot.on_message(filters.command("nhentai"))
async def nhentai_handler(client, message):
    status = await message.reply("Processing... Please wait.")
    if len(message.command) == 1:
        return await status.edit("Please provide the doujin's code or URL.")
    code = message.command[1]
    try:
        doujin = await Nhentai().get(code)
    except Exception:
        await status.edit("Doujin not found on nhentai.")
        return

    doujin_info = generate_doujin_info(doujin)
    await status.edit(f"Processing... Downloading [{doujin.title}]({doujin.url})")

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
        doujin = await Nhentai().get(code)
    except Exception:
        await status.edit("Doujin not found on nhentai.")
        return

    doujin_info = generate_doujin_info(doujin)
    await status.edit(f"Processing... [{doujin.title}]({doujin.url})")

    graph_link = await generate_telegraph_link(doujin)
    graph_link = graph_link or doujin.read_url
    graph_post = f"[{doujin.title}]({graph_link})"
    doujin_info = doujin_info.replace(doujin_info.split("\n")[0].strip(), graph_post)

    await status.edit(doujin_info, parse_mode=ParseMode.MARKDOWN)
