import re

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.db import dB
from bot.utils.functions import string_similarity

# Mapping of request groups to channels
rchats = {
    -1001817093909: -1002053736857,
    -1001973094139: -1001643268493,
    -1001568226560: -1001821705224,
}


# Lists of request groups and channels
rgroups = list(rchats.keys())
rchannels = list(rchats.values())
phub_group = -1001817093909


# Command handler for requests
@Client.on_message(
    filters.command("request", prefixes=["/", "!", "#", "."]) & filters.chat(rgroups)
)
async def handle_requests(client, message):
    reply = message.reply_to_message
    user_mention = message.from_user.mention

    if reply:
        text = get_request_from_text(reply.text)
        user_mention = message.reply_to_message.from_user.mention
    elif len(message.command) > 1:
        _, text = map(str.strip, message.text.split(" ", 1))
    else:
        return

    chat_to_send = rchats.get(message.chat.id)
    if chat_to_send is None:
        return

    reply_id = (reply or message).id
    req_db = await dB.get_key("REQUESTDB") or {}
    req_db_key = str(message.chat.id)
    req_db.setdefault(req_db_key, [])
    users_requests = [
        req for req in req_db[req_db_key] if req["user_id"] == message.from_user.id
    ]
    duplicate_req = next(
        (
            req
            for req in req_db[req_db_key]
            if re.search(re.escape(text), req["text"], re.I)
        ),
        None,
    )

    if duplicate_req:
        await message.reply(
            f"Hello, {user_mention}. Your request has already been made in the channel.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "View Status",
                            url=f"https://t.me/c/{str(chat_to_send).replace('-100', '')}/{duplicate_req['request_message_id']}",
                        )
                    ]
                ]
            ),
        )
        return

    if len(users_requests) >= 2:
        await message.reply(
            f"Hello, {user_mention}. You've already sent enough pending requests. Please wait until they are addressed before submitting another one."
        )
        return

    if message.chat.id == phub_group:
        namelinks = await dB.get_key("PHUB_NAMELINKS") or {}
        matches = [
            (name, link)
            for name, link in namelinks.items()
            if string_similarity(text, name) > 80.0
        ]
        if matches:
            matching_text = "\n".join(
                f"→[{name}]({link})" for name, link in matches[:10]
            )
            await client.send_message(
                message.chat.id,
                f"Hey, there! I discovered some results that match your request.\n\n{matching_text}\n\n<b>Have you found your request in any of these matches?</b>",
                reply_markup=(
                    (
                        InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        "Yes", f"reqs_yes_{message.from_user.id}"
                                    ),
                                    InlineKeyboardButton(
                                        "No", f"reqs_no_{message.from_user.id}"
                                    ),
                                ]
                            ]
                        )
                    )
                    if len(req_db[req_db_key]) < 15
                    else None
                ),
                reply_to_message_id=reply_id,
            )
            return

    if len(req_db[req_db_key]) >= 15:
        await message.reply(
            f"Hello, {user_mention}. This channel only accepts 15 pending requests at a time, and the quota is already full. Please wait until some have been addressed by the administrators before sending another one."
        )
        return

    text_to_send = f"<b>STATUS:</b> #PENDING\n\n<b>Requestor:</b> {user_mention} [<code>{(reply or message).from_user.id}</code>]\n<b>Request:</b> <code>{text}</code>"
    buttons_to_send = [
        [InlineKeyboardButton("Request Message", url=(reply or message).link)],
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
        chat_to_send,
        text_to_send,
        reply_markup=InlineKeyboardMarkup(buttons_to_send),
    )

    await client.send_message(
        message.chat.id,
        f"Hello, {user_mention}. Your request <code>{text}</code> was submitted.\n\n<b>Please keep in mind that administrators might be busy, so it may take some time.</b>",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("View Status", url=request_message.link)]]
        ),
        reply_to_message_id=reply_id,
    )
    req_db[req_db_key].append(
        {
            "request_message_id": request_message.id,
            "message_id": (reply or message).id,
            "user_mention": user_mention,
            "user_id": (reply or message).from_user.id,
            "text": text,
        }
    )
    await dB.update_key("REQUESTDB", req_db, upsert=True)


# Callback query handler for request actions
@Client.on_callback_query(
    filters.regex("reqs_(yes|no|completed|rejected|unavailable|already_available)")
)
async def handle_request_action(client, callback):
    message = callback.message
    splited = callback.data.split("_")
    re_group = str(message.chat.id) if message.chat.id in rgoups else next(
        str(key) for key, value in rchats.items() if value == message.chat.id
    )
    req_db = await dB.get_key("REQUESTDB") or {}
    req_db.setdefault(re_group, [])

    if splited[1] in ("yes", "no"):
        if int(splited[2]) != callback.from_user.id:
            await callback.answer("Sorry, this option is not for you.", show_alert=True)
            return

        if splited[1] == "yes":
            await callback.answer(
                "Got it! Thank you for your response.", show_alert=True
            )
            await message.edit("\n\n".join(message.text.html.split("\n\n")[:-1]))
        elif len(req_db[re_group]) >= 15:
            await callback.message.edit(
                f"Hello, {user_mention}. This channel only accepts 15 pending requests at a time, and the quota is already full. Please wait until some have been addressed by the administrators before sending another one.",
            )
        elif (
            splited[1] == "no"
            and message.reply_to_message
            and message.chat.id in rchats
        ):
            await callback.answer(
                "Understood! Your request will be submitted.", show_alert=True
            )
            text = get_request_from_text(message.reply_to_message.text)
            text_to_send = f"<b>STATUS:</b> #PENDING\n\n<b>Requestor:</b> {message.reply_to_message.from_user.mention} [<code>{message.reply_to_message.from_user.id}</code>]\n<b>Request:</b> <code>{text}</code>"
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
                f"Hi {message.reply_to_message.from_user.mention}, your request <code>{text}</code> has been submitted.\n\n<b>Please note that admins might be busy, so it may take some time.</b>",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("View Status", url=request_message.link)]]
                ),
            )
            await message.delete()
            req_db[re_group].append(
                {
                    "request_message_id": request_message.id,
                    "message_id": message.id,
                    "user_id": message.reply_to_message.from_user.id,
                    "user_mention": message.reply_to_message.from_user.mention,
                    "text": text,
                }
            )
            await dB.update_key("REQUESTDB", req_db, upsert=True)
        else:
            await callback.answer(
                "Oops! Something unexpected happened.",
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

    request = next(
        req
        for req in req_db[re_group]
        if req["request_message_id"] == callback.message.id
    )
    re_group_chat = await client.get_chat(int(re_group))
    action = "_".join(splited[1:])
    to_send = f'<i><u><b>[{re_group_chat.title}]:</b></u></i>\n\n<i>Your request "{request["text"]}" is {action}.</i>'
    to_edit = f"<b>STATUS:</b> #{action.upper()}\n\n<b>Requestor:</b> {request['user_mention']} [<code>{request['user_id']}</code>]\n<b>Request:</b> <code>{request['text']}</code>"

    try:
        await client.send_message(request["user_id"], to_send)
    except BaseException:
        pass

    await message.edit_text(
        to_edit,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Request Message",
                        url=f"https://t.me/c/{re_group.replace('-100', '')}/{request['message_id']}",
                    )
                ]
            ]
        ),
    )
    req_db[re_group].remove(request)
    await dB.update_key("REQUESTDB", req_db)


# Function to extract request text from a message
def get_request_from_text(text):
    request_regex = "(#|!|/|.)?[rR][eE][qQ][uU][eE][sS][tT] "
    if request_match := re.match(request_regex, text):
        text = text.replace(request_match.group(), "").strip()
    return text
