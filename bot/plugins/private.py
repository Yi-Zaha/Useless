import asyncio
import re
import time

from pyrogram import filters
from pyrogram.errors import FloodWait, PeerIdInvalid, UserIsBlocked
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import CACHE_CHAT, LOG_CHAT, OWNER_ID, SUDOS, StartTime, bot
from bot.config import Config
from bot.logger import LOGGER
from bot.utils.db import udB
from bot.utils.functions import (
    b64_decode,
    generate_share_url,
    get_chat_invite_link,
    get_chat_messages,
    is_user_subscribed,
    readable_time,
)

SUBS_CHANNEL = Config.get("SUBS_CHANNEL", -1001606385356)


@bot.on_message(filters.private & filters.command("start"))
async def on_start(client, message):
    text = message.text.split(" ", 1)[1] if len(message.text.split(" ")) > 1 else ""

    if text.startswith("Sharem-"):
        b64_code = text.split("-")[1]
        b64_string = b64_decode(b64_code)
        if not b64_string:
            return await pm_start(client, message)

        if not await is_user_subscribed(message.from_user.id, SUBS_CHANNEL):
            join_url = await get_chat_invite_link(SUBS_CHANNEL)
            join_button = InlineKeyboardButton("Join", url=join_url)
            retry_button = InlineKeyboardButton(
                "Retry", url=f"https://t.me/{client.me.username}?start={text}"
            )
            reply_markup = InlineKeyboardMarkup([[join_button, retry_button]])
            return await message.reply(
                f"<i>Hi {message.from_user.mention}.\nIn order to get the files you need to join my channel first.</i>",
                reply_markup=reply_markup,
            )

        status = await message.reply("Please wait a moment...")
        state, ids = b64_string.split("_")
        first_msg_id, last_msg_id = map(int, ids.split("-"))
        protect_content = "ProtectedBatchMsgs" == state.strip()

        try:
            messages = await get_chat_messages(
                chat=CACHE_CHAT,
                first_msg_id=first_msg_id,
                last_msg_id=last_msg_id + 1,
            )
        except Exception as e:
            return await status.edit(
                f"<b>Oops! Something went wrong.</b>\n\n<code>{type(e).__name__}: {e}</code>"
            )

        sent_ids = []
        for msg in messages:
            if not message:
                continue
            try:
                sent = (
                    await msg.copy(
                        message.chat.id,
                        caption=getattr(msg.caption, "html", None),
                        protect_content=protect_content,
                    )
                    if msg.media
                    else await client.send_message(
                        message.chat.id,
                        msg.text.markdown,
                        protect_content=protect_content,
                    )
                )
                sent_ids.append(sent.id)
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 5)
                sent = (
                    await msg.copy(
                        message.chat.id,
                        caption=getattr(msg.caption, "html", None),
                        protect_content=protect_content,
                    )
                    if msg.media
                    else await client.send_message(
                        message.chat.id,
                        msg.text.markdown,
                        protect_content=protect_content,
                    )
                )
            except Exception:
                pass

        await status.delete()

        if "TimedBatchMsgs" == state.strip():
            temp_msg = await client.send_message(
                message.chat.id, "*Forward or save these messages somewhere."
            )
            await asyncio.sleep(5 * 60)
            try:
                await client.delete_messages(message.chat.id, sent_ids)
            except FloodWait as fw:
                await asyncio.sleep(fw.value)
                await client.delete_messages(message.chat.id, sent_ids)
            except Exception as e:
                LOGGER(__name__).info(str(e))
            await temp_msg.delete()
    else:
        await pm_start(client, message)


async def pm_start(client, message):
    uptime = readable_time(time.time() - StartTime)
    s_time = time.time()
    status = await message.reply_text("<i>...</i>")
    t_taken = (time.time() - s_time) * 1000
    ping = f"{t_taken:.3f}"

    start_text = (
        f"Hi {message.from_user.mention}. I am working for Pornhwa Hub.\n"
        f"You can contact my owner through me.\n\n"
        f"<b>»Uptime</b>: <code>{uptime}</code>\n"
        f"<b>»Ping</b>: <code>{ping} ms</code>"
    )

    channel_link = await get_chat_invite_link(SUBS_CHANNEL)
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("My Channel", url=channel_link),
                InlineKeyboardButton("My Owner", user_id=OWNER_ID),
            ]
        ]
    )

    await status.edit_text(start_text, reply_markup=reply_markup)


@bot.on_message(filters.private & filters.incoming, group=-1)
async def pm_handler(client, message):
    user = message.from_user

    if not await udB.get_key("id", user.id):
        await udB.add_user(user)
        name = user.first_name + " " + (user.last_name or "").strip()
        username = "@" + user.username if user.username else "N/A"
        profile_link = f"[Click Here](tg://user?id={user.id})"
        message = (
            "<b>Someone Started Me❗</b>\n\n"
            f"<b>›› Name →</b> <code>{name}</code>\n"
            f"<b>›› Username →</b> <code>{username}</code>\n"
            f"<b>›› Profile Link →</b> {profile_link}"
        )
        await client.send_message(LOG_CHAT, message)


no_forward_cmds = ["start"]


@bot.on_message(filters.private & filters.incoming & ~filters.user(SUDOS), group=1)
async def forwardpms_handler(_, message):
    if message.command and message.command[0] in no_forward_cmds:
        return None
    await message.forward(OWNER_ID)


@bot.on_message(filters.reply & filters.private & filters.user(OWNER_ID))
async def reply_to_pms(client, message):
    reply = message.reply_to_message
    peer = None

    if reply.forward_from:
        peer = reply.forward_from.username or reply.forward_from.id

    elif reply.forward_sender_name:
        async for user in udB.find():
            if reply.forward_sender_name == user["name"]:
                peer = user["username"] or user["id"]
                break
        else:
            return await message.continue_propagation()

    else:
        return message.continue_propagation()

    try:
        user = await client.get_users(peer)
    except PeerIdInvalid:
        LOGGER(__name__).info(f"Couldn't get peer ({peer}), aborted replying to pm.")
        return message.continue_propagation()

    try:
        await client.copy_message(peer, message.chat.id, message.id)
    except UserIsBlocked:
        await client.send_message(
            LOG_CHAT,
            "<b>Someone has Blocked Me❗</b>\n\n"
            f"<b>›› Name →</b> <code>{user.first_name + (user.last_name or '')}</code>\n<b>›› Username →</b> <code>{'@'+user.username if user.username else 'N/A'}</code>\n<b>›› Profile Link →</b> [Click Here](tg://user?id={user.id})",
        )
        await udB.del_key("id", user.id)
    except Exception as e:
        LOGGER(__name__).error(f"Got Error while replying to a pm: {e}", exc_info=True)

    return message.continue_propagation()


@bot.on_message(filters.command("storefiles") & filters.user(SUDOS))
async def storefiles_event(client, message):
    while True:
        try:
            msg1 = await client.ask(
                message.chat.id,
                "Forward (or Send the link of) the first message from the DB channel.",
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60,
            )
        except Exception as e:
            LOGGER(__name__).info(str(e))
            return
        msg1_id = await get_msg_id(msg1)
        if msg1_id:
            break
        else:
            await msg1.reply(
                "Invalid Response, this message is not from my DB channel. Send the correct message again."
            )

    while True:
        try:
            msg2 = await client.ask(
                message.chat.id,
                "Forward (or Send the link of) the last message from the DB channel.",
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60,
            )
        except Exception as e:
            LOGGER(__name__).info(str(e))
            return
        msg2_id = await get_msg_id(msg2)
        if msg2_id:
            break
        await msg2.reply(
            "<i>Invalid Response, this message is not from my DB channel. Send the correct message again.</i>"
        )

    normal_url = generate_share_url("normal", msg1_id, msg2_id)
    protect_url = generate_share_url("protect", msg1_id, msg2_id)
    expiry_url = generate_share_url("expiry", msg1_id, msg2_id)

    buttons = []
    buttons.append(
        [
            InlineKeyboardButton(
                "🔗 URL",
                url=normal_url,
            )
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                "🔒 Protected URL",
                url=protect_url,
            )
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                "⏳ Timed URL",
                url=expiry_url,
            )
        ]
    )

    await message.reply(
        "<i>Here's your stored messages URL ↓</i>",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def get_msg_id(msg):
    if getattr(msg.forward_from_chat, "id", None) == CACHE_CHAT:
        return msg.forward_from_message_id

    elif msg.forward_sender_name:
        return

    elif msg.text:
        db_chat = await bot.get_chat(CACHE_CHAT)
        regex = re.compile("https://t.me/(?:c/)?(.*)/(\\d+)")
        match = regex.match(msg.text)
        if not match:
            return
        chat = match.group(1)
        msg_id = int(match.group(2))
        if chat.isdigit():
            if f"-100{chat}" == str(CACHE_CHAT):
                return msg_id
        elif chat.lower() == db_chat.username.lower():
            return msg_id
