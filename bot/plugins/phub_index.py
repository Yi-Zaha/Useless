import asyncio
import string

from pyrogram import filters

from bot import SUDOS, bot
from bot.config import Config
from bot.logger import LOGGER
from bot.utils.db import dB
from bot.utils.functions import get_chat_messages

PHUB_CHANNEL = Config.get("PORNHWA_HUB", -1001705095281)
INDEX_CHANNEL = Config.get("PORNHWA_HUB_INDEX", -1001749847496)
UPDATING_INDEX = None


@bot.on_message(filters.command("updateindex") & filters.user(SUDOS))
async def update_index(client, message):
    status = await message.reply("Processing...")
    try:
        await update_phub_index()
        await status.edit("Successfully updated the PH Index.")
    except Exception:
        LOGGER(__name__).info("Error raised in updating PH Index", exc_info=True)
        await status.edit("Updating PH Index raised some errors (Check Logs).")


@bot.on_message(filters.channel & filters.chat(PHUB_CHANNEL))
async def on_phub_handler(client, message):
    await dB.update_key("PH_LAST_ID", message.id + 1, upsert=True)
    if "→Status:" in str(message.caption):
        try:
            await update_phub_index()
        except Exception:
            LOGGER(__name__).info("Error raised in updating PH Index", exc_info=True)


async def update_phub_index():
    global UPDATING_INDEX
    if UPDATING_INDEX is True:
        return
    UPDATING_INDEX = True

    index_posts = await get_chat_messages(
        INDEX_CHANNEL, first_msg_id=62, last_msg_id=89
    )
    index = {"#": {}, **{alpha: {} for alpha in string.ascii_uppercase}}
    posts = {}

    messages = await get_chat_messages(
        PHUB_CHANNEL, first_msg_id=2, last_msg_id=await dB.get_key("PH_LAST_ID")
    )

    for message in messages:
        if "→Status:" in str(message.caption):
            name = message.caption.splitlines()[0].replace("─=≡", "").replace("≡=─", "").strip()
            chat_id = str(message.chat.id).replace("-100", "")
            link = f"https://t.me/c/{chat_id}/{message.id}"
            if name[0].isalpha():
                index_key = name[0]
            else:
                index_key = "#"
            
            if "releasing" in message.caption.lower():
                tick = "🔷"
            elif "finished" in message.caption.lower():
                tick = "🔶"
            elif "incomplete" in message.caption.lower():
                tick = "♦️"

            i_text = f"{tick} <a href='{link}'>{name}</a>\n"
            index[index_key][name] = i_text

    for f in sorted(index):
        texts = index[f]
        if f not in posts:
            posts[f] = f"<b>⛩️ {f}-{f}-{f} ⛩️</b>\n\n"
            for name in sorted(texts):
                text = texts[name]
                posts[f] += text

    updated = []
    for index_post, post_text in zip(index_posts, posts.values()):
        if not post_text or index_post.text.html == post_text:
            continue

        try:
           await index_post.edit(post_text)
           updated.append(index_post.id)
        except Exception as e:
            print(f"Error in updating PH Index post id {index_post_id}: {e}")

    UPDATING_INDEX = False
    return updated
