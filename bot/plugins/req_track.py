import re
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, MessageEntityType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot import bot
from bot.utils.db import dB


# Mapping of request groups to channels
rchats = {
    -1001817093909: -1001459727128,
    -1001973094139: -1001643268493,
    -1001568226560: -1001821705224,
}


# Lists of request groups and channels
rgroups = list(rchats.keys())
rchannels = list(rchats.values())
phub_group = -1001568226560


# Command handler for requests
@bot.on_message(
    filters.command("request", prefixes=["/", "!", "#", "."]) & filters.chat(rgroups)
)
async def handle_requests(client, message):
    reply = message.reply_to_message
    if reply:
        text = get_request_from_text(reply.text)
        user_mention = reply.from_user.mention
    elif len(message.command) > 1:
        _, text = message.text.split(" ", 1)
        user_mention = message.from_user.mention
    else:
        return

    reply_id = (reply or message).id

    if message.chat.id == phub_group:
        namelinks = await dB.get_key("PHUB_NAMELINKS") or {}
        matches = [(name, link) for name, link in namelinks.items() if re.search(text, name, flags=re.I)]
        if matches:
            matching_text = "\n".join(f"→[{name}]({link})" for name, link in matches[:5])
            await client.send_message(
                message.chat.id,
                f"Hey, I found some matching results for your requests.\n\n{matching_text}\n\n<b>Did you find your request in any of these matches?</b>",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Yes", f"reqs_yes_{(reply or message).from_user.id}")],
                        [InlineKeyboardButton("No", f"reqs_no_{(reply or message).from_user.id}")]
                    ]
                ),
                reply_to_message_id=reply_id,
            )

    chat_to_send = rchats.get(message.chat.id)
    if chat_to_send is not None:
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
            reply_to_message_id=reply_id,
        )


# Callback query handler for request actions
@bot.on_callback_query(filters.regex("reqs_(yes|no|completed|rejected|unavailable|already_available)"))
async def handle_request_action(client, callback):
    message = callback.message
    splited = callback.data.split("_")
    action = splited[1]

    if action in ("yes", "no"):
        if int(splited[2]) != callback.from_user.id:
            return await callback.answer(
                f"Sorry, this button is not meant for you.",
                show_alert=True
            )

        if action == "yes":
            await callback.answer(
                f"Okay! Thank you for answering.",
                show_alert=True
            )
            await message.edit("\n\n".join(message.text.split("\n\n")[:-1])) # Removing the last line
        elif action == "no" and message.reply_to_message and message.chat.id in rchats:
            await callback.answer(
                "Okay! Your request shall be submitted then.",
                show_alert=True
            )
            request = get_request_from_text(message.reply_to_message.text)
            text_to_send = f"<b>Request By:</b> {message.reply_to_message.from_user.mention}\n\n<code>{request}</code>"
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
                rchats[message.chat.id],
                text_to_send,
                reply_markup=InlineKeyboardMarkup(buttons_to_send),
            )
            await message.reply_to_message.reply(
                f"Hi {user_mention}, your request for <code>{text}</code> has been submitted to the admins.\n\n<b>Please note that admins might be busy, so it may take some time.</b>",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("View Status", url=request_message.link)]]
                ),
            )
            await message.delete()
        else:
            await callback.answer(
                "Something unexpected occurred!",
                show_alert=True,
            )
        return

    try:
        sender = await client.get_chat_member(message.chat.id, callback.from_user.id)
    except BaseException:
        sender = None

    if not sender or sender.status not in [
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    ]:
        return await callback.answer(
            f"Sorry, you don't have the permission to perform this action {callback.from_user.first_name}",
            show_alert=True,
        )

    user_id = None
    for entity in message.entities:
        if entity.type == MessageEntityType.TEXT_MENTION:
            user_id = entity.user.id
            break

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


# Function to extract request text from a message
def get_request_from_text(text):
    request_regex = "(#|!|/|.)?[rR][eE][qQ][uU][eE][sS][tT] "
    request_match = re.match(request_regex, text)
    if request_match:
        text = text.replace(request_match.group(), "").strip()
    return text
