import re

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, MessageEntityType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import bot

rchats = {
    -1001817093909: -1001459727128,
    -1001973094139: -1001643268493,
    -1001568226560: -1001821705224,
}

rgroups = list(rchats.keys())  # requestGroups
rchannels = list(rchats.values())  # requestChannels


@bot.on_message(
    filters.command("request", prefixes=["/", "!", "#", "."]) & filters.chat(rgroups)
)
async def handle_requests(client, message):
    reply = message.reply_to_message
    if reply:
        text = get_request_from_text(reply.text)
        user_mention = reply.from_user.mention
    else:
        _, text = message.text.split(" ", 1)
        user_mention = message.from_user.mention

    chat_to_send = rchats[message.chat.id]
    text_to_send = f"<b>Request By:</b> {user_mention}\n\n<code>{text}</code>"
    buttons_to_send = [
        [InlineKeyboardButton("Request Message", url=message.link)],
        [
            InlineKeyboardButton("Done", "reqs_completed"),
            InlineKeyboardButton("Reject", "reqs_rejected"),
        ],
        [
            InlineKeyboardButton("Unavailable", "reqs_unavailable"),
            InlineKeyboardButton("Already Available", "reqs_already_available"),
        ],
    ]

    request_message = await client.send_message(
        chat_to_send, text_to_send, reply_markup=InlineKeyboardMarkup(buttons_to_send)
    )

    await client.send_message(
        message.chat.id,
        f"Hi {user_mention}, your request for <code>{text}</code> has been submitted to the admins.\n\n<b>Please note that admins might be busy, so it may take some time.</b>",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("View Status", url=request_message.link)]]
        ),
        reply_to_message_id=(reply or message).id,
    )


@bot.on_callback_query(filters.regex("reqs_(.*)"))
async def handle_request_action(client, callback):
    message = callback.message

    try:
        sender = await client.get_chat_member(message.chat.id, callback.from_user.id)
    except BaseException:
        sender = None

    if not sender or sender.status not in [
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    ]:
        return await callback.answer(
            f"Sorry, you don't have the permission to perform this action, {callback.from_user.first_name}",
            show_alert=True,
        )

    action = callback.matches[0].group(1).replace("_", " ")
    user_id = None
    user_name = message.text.splitlines()[0].replace("Request By:", "").strip()
    for entity in message.entities:
        if entity.type == MessageEntityType.TEXT_MENTION:
            user_id = entity.user.id
            break
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
    message_text = message.text.html.replace("<code>", "").replace("</code>", "")
    crequest = message_text.split("\n")[-1].strip()
    chat = await client.get_chat(
        next(g for g, c in rchats.items() if c == message.chat.id)
    )
    to_send = f'<i><u><b>[{chat.title}]:</b></u></i>\n\n<i>Your request for "{crequest}" has been {action}.</i>'
    to_edit = f"<b>▼{action.upper()}▼</b>\n\n<s>{message_text}</s>"

    if user_id:
        try:
            await client.send_message(user_id, to_send)
        except BaseException:
            pass

    await message.edit_text(to_edit)


def get_request_from_text(text):
    request_regex = "(#|!|/|.)?[rR][eE][qQ][uU][eE][sS][tT] "
    request_match = re.match(request_regex, text)
    if request_match:
        text = text.replace(request_match.group(), "").strip()
    return text
