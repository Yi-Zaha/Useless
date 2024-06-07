import asyncio
import copy
import os
import re
from contextlib import suppress

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified, PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from SafoneAPI import SafoneAPI

from bot import SUDOS
from bot.helpers import ani
from bot.logger import LOGGER
from bot.plugins.phub_index import get_chat_by_invite_link, parse_message_caption
from bot.plugins.pornhwa import PS, process_bulk
from bot.utils import BULK_PROCESS, AioHttp
from bot.utils.db import dB, pdB
from bot.utils.functions import (
    ask_callback_options,
    ask_message,
    get_chat_invite_link,
    get_function_args,
    get_random_id,
    is_url,
    split_list,
)

safone_api = SafoneAPI()
data_source_chat = -1001783376856
data_ids = [37423, 37424]
bio_for_channel = [37425]
first_msg_media = (
    "CAACAgUAAxkBAAEgAAE3ZiDt6OwYEanpg8W6JgMlkGBKr1cAAhYAA0NzyRKB2L8htoZV3B4E"
)
bulkp_options = {
    "manga_url": {"name": "Manga Url", "required": True, "check": is_url},
    "manga_name": {"name": "Manga Name"},
    "chat_id": {"name": "Chat ID", "check": lambda x: str.isdigit(x[1:]), "cast": int},
    "chat_pic": {
        "name": "Chat Pic",
        "input_filter": (filters.photo | filters.text | filters.document),
        "check": lambda x: is_url(x) or os.path.exists(x),
    },
    "psub_url": {"name": "PSub Url", "check": is_url},
    "merge_limit": {"name": "Merge Limit", "check": str.isdigit, "cast": int},
    "pdf_pass": {"name": "Pdf Password", "spec": "No Spaces!"},
    "start_from": {"name": "Start Chapter Url", "check": is_url},
    "end_to": {"name": "End Chapter Url", "check": is_url},
    "protect_content": {"value": True, "name": "Protect Content", "type": bool},
    "showpass": {"value": False, "name": "Show Password", "type": bool},
    "comick_vol": {"value": False, "name": "Use Volumes (Comick Only)", "type": bool},
}

state = {}


@Client.on_message(filters.command(["phub_post"]) & filters.user(SUDOS))
async def update_post_channel(client, message):
    post_m_id = None
    if len(message.command) != 1 and message.command[1].isdigit():
        post_m_id = int(message.command[1])
        manga_url = message.command[2] if len(message.command) > 2 else None
        chat_id = message.command[3] if len(message.command) > 3 else None
    else:
        manga_url = message.command[1] if len(message.command) > 1 else None
        chat_id = message.command[2] if len(message.command) > 2 else None

    if chat_id and not chat_id[1:].isdigit():
        return await message.reply("Chat ID should be a valid integer.")
    if chat_id:
        chat_id = int(chat_id)

    if post_m_id:
        post_db = await dB.get_key("PHUB_POST_DB")
        post = next(
            (p for p in post_db.get("posts", []) if p.get("message_id") == post_m_id),
            None,
        )
        if not post:
            return await message.reply("Message ID does not match any post.")
        old_chat_id = post.get("fchannel", {}).get("chat_id")
        if not manga_url:
            if not old_chat_id:
                post_chat = await get_chat_by_invite_link(
                    client, post["fchannel"]["invite_link"]
                )
                if post_chat:
                    post["fchannel"]["chat_id"] = old_chat_id = post_chat.id
                    try:
                        await post_chat.leave()
                    except Exception as e:
                        LOGGER(__name__).error(
                            f"[UB] Error leaving chat [{chat_id}]: {e}"
                        )
                    await dB.update_key("PHUB_POST_DB", post_db)

        matching_sub = await anext(pdB.all_subs({"chat": old_chat_id}), {})
        manga_url = manga_url or matching_sub.get("url")
    else:
        if manga_url:
            try:
                PS.guess_ps(manga_url)
            except ValueError:
                await message.reply("The url you gave is invalid.")
                return

    buttons = [
        InlineKeyboardButton(
            "Set Manga Url" if not manga_url else "Change Manga Url",
            f"up_phub_post:manga_url:{message.from_user.id}",
        ),
        *[
            InlineKeyboardButton(
                (
                    option_info["name"]
                    if option_info.get("type") != bool
                    else f"{option_info['name']}: {'Enabled' if option_info.get('value') else 'Disabled'}"
                ),
                f"up_phub_post:{option}:{message.from_user.id}",
            )
            for option, option_info in list(bulkp_options.items())[1:]
        ],
    ]
    buttons = split_list(buttons, 2)
    buttons.append(
        [
            InlineKeyboardButton(
                "FINISH ››", f"up_phub_post:finish:{message.from_user.id}"
            )
        ]
    )

    bulkp_opts = state.setdefault(
        message.chat.id + message.id, copy.deepcopy(bulkp_options)
    )
    if manga_url:
        bulkp_opts["manga_url"]["value"] = manga_url
    if chat_id:
        bulkp_opts["chat_id"]["value"] = chat_id
    bulkp_opts["merge_limit"]["value"] = 10

    reply_message = (
        "<b><u>─=≡ Update Phub Post's Channel ≡=─</u></b>"
        if post_m_id
        else "<b><u>─=≡ Create Phub Post ≡=─</u></b>"
    )
    required_options = ", ".join(
        [
            option_info["name"]
            for option_info in bulkp_options.values()
            if option_info.get("required", False)
        ]
    )
    reply_message += (
        f"\n<i>Utilize the buttons below to adjust upload to your preferrence.\n"
    )
    reply_message += (
        f"\n<b>››Post ID:</b> <code>{post_m_id}</code>" if post_m_id else ""
    )
    reply_message += "\n"
    reply_message += "\n".join(
        f"<b>››{bulkp_opt['name']}:</b> <code>{(' (Required)' if bulkp_opt.get('required') else ' (Optional)') if bulkp_opt.get('value') is None else bulkp_opt['value']}</code>"
        for bulkp_opt in bulkp_opts.values()
        if bulkp_opt.get("type") != bool
    )

    await message.reply(
        reply_message.strip(), reply_markup=InlineKeyboardMarkup(buttons), quote=True
    )


@Client.on_callback_query(filters.regex(r"^up_phub_post:.*"))
async def up_phub_post(client, callback):
    _, option, user_id = callback.data.split(":")
    user_id = int(user_id)

    if callback.from_user.id != user_id:
        await callback.answer("Sorry, this is not for you.", show_alert=True)
        return

    text = callback.message.text.html
    reply_markup = callback.message.reply_markup
    state_key = callback.message.chat.id + callback.message.id
    bulkp_opts = state.get(state_key, {})

    if not bulkp_opts:
        bulkp_opts = state.setdefault(state_key, copy.deepcopy(bulkp_options))

        async def set_bulkp_opt(option, option_info):
            nonlocal text
            nonlocal bulkp_opts
            option_in_text = re.search(
                rf"<b>››{option_info['name']}:</b> <code>(.*)</code>", text
            )
            if option_in_text and not option_in_text.group(1).startswith(
                (" (Optional)", " (Required)")
            ):
                if option == "chat_pic":
                    text = text.replace(f"\n{option_in_text.group()}", "")
                else:
                    bulkp_opts[option]["value"] = option_info.get("cast", str)(
                        option_in_text.group(1)
                    )

        await asyncio.gather(
            *[
                set_bulkp_opt(option, option_info)
                for option, option_info in bulkp_opts.items()
            ]
        )

    if "active" in bulkp_opts:
        if bulkp_opts["active"] == option:
            with suppress(Exception):
                await client.lisent.Cancel(
                    str(callback.message.chat.id + callback.message.id + user_id)
                )
            del bulkp_opts["active"]
            await callback.answer("Task cancelled.")
            return
        else:
            await callback.answer(
                "Please finish the current task first.", show_alert=True
            )
            return

    def find_button_in_reply_markup():
        for row_index, row in enumerate(reply_markup.inline_keyboard):
            for button_index, button in enumerate(row):
                if callback.data == button.callback_data:
                    return (row_index, button_index)

    option_info = bulkp_opts.get(option)
    if not option_info:
        required_options = []
        for option, option_info in bulkp_opts.items():
            if option_info.get("required") and option_info.get("value") is None:
                required_options.append(option_info["name"])
                await callback.answer(
                    f"Set {option_info['name'].lower()} before continuing.",
                    show_alert=True,
                )
                return

        post_id = re.search(rf"<b>››Post ID:</b> <code>(.*)</code>", text)
        post_id = int(post_id.group(1)) if post_id else None

        if required_options:
            await callback.answer(
                f"Set {required_options[0].lower()} before continuing.", show_alert=True
            )
            return

        if isinstance(bio_for_channel[0], int):
            bio_for_channel.insert(
                0, await client.get_messages(data_source_chat, bio_for_channel[0])
            )

        try:
            await client.ub.resolve_peer(client.me.id)
        except PeerIdInvalid:
            await client.ub.resolve_peer(client.me.username)

        await callback.answer()
        callback.message = await callback.edit_message_text(
            callback.message.text.html.replace(
                f"{callback.message.text.html.splitlines()[1]}\n\n", ""
            )
        )
        with suppress(Exception):
            await callback.message.pin(both_sides=True)
        try:
            await process_up_phub_post(client, callback, bulkp_opts, post_id=post_id)
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            LOGGER(__name__).exception(e)
            await callback.edit_message_text(
                f"{callback.message.text.html}\n\n<b>Oops! Something went wrong.</b>\n\n<code>{type(e).__name__}: {e}</code>"
            )
        finally:
            with suppress(Exception):
                await callback.message.unpin()
            del state[state_key]
        return

    if option_info.get("type") == bool:
        row_index, button_index = find_button_in_reply_markup()
        reply_markup.inline_keyboard[row_index][
            button_index
        ].text = reply_markup.inline_keyboard[row_index][button_index].text.replace(
            "Enabled" if option_info["value"] else "Disabled",
            "Disabled" if option_info["value"] else "Enabled",
        )
        option_info["value"] = not option_info["value"]
        if text != callback.message.text:
            await callback.edit_message_text(text, reply_markup=reply_markup)
        else:
            await callback.edit_message_reply_markup(reply_markup)
        await callback.answer()

    else:
        bulkp_opts["active"] = option
        await callback.answer(
            f"Okay, text me the {option_info['name'].lower()}."
            + option_info.get("spec", "")
        )
        listened_message = await client.listen.Message(
            filters=option_info.get("input_filter", filters.text)
            & filters.chat(callback.message.chat.id)
            & filters.user(callback.from_user.id),
            id=str(callback.message.chat.id + callback.message.id + user_id),
            timeout=90,
        )
        if not listened_message:
            bulkp_opts.pop("active", None)
            return
        if listened_message.photo or listened_message.document:
            if (
                listened_message.document
                and "image" not in listened_message.document.mime_type
            ):
                await listened_message.reply(
                    f"Invalid Value for {option_info['name'].lower()}.", quote=True
                )
                del bulkp_opts["active"]
                return
            option_info["value"] = input_value = await listened_message.download()
        if listened_message.text:
            input_value = listened_message.text.strip()
        option_in_text = re.search(
            rf"<b>››{option_info['name']}:</b> <code>(.*)</code>", text
        )
        if (
            option_in_text
            and not option_info.get("required")
            and input_value in ["NA", "/remove"]
        ):
            text = text.replace(
                f"\n{option_in_text.group()}" "",
            )
            del option_info["value"]
        else:
            if option_info.get("check") and not option_info["check"](input_value):
                await listened_message.reply(
                    f"Invalid Value for {option_info['name'].lower()}.", quote=True
                )
                del bulkp_opts["active"]
                return
            if option_in_text:
                text = text.replace(
                    option_in_text.group(),
                    option_in_text.group().replace(
                        option_in_text.group(1), input_value
                    ),
                )
            else:
                text = (
                    callback.message.text.html
                    + f"\n<b>››{option_info['name']}:</b> <code>{input_value}</code>"
                )
            option_info["value"] = option_info.get("cast", str)(input_value)

        await callback.edit_message_text(
            text,
            reply_markup=reply_markup,
        )

        del bulkp_opts["active"]


async def process_up_phub_post(client, callback, bulkp_opts, post_id=None):
    post = None
    manga_url = bulkp_opts["manga_url"].get("value")
    chat_id = bulkp_opts["chat_id"].get("value")
    manga_name = bulkp_opts["manga_name"].get("value")
    chat_pic = bulkp_opts["chat_pic"].get("value", "")
    psub_url = bulkp_opts["psub_url"].get("value")
    post_db = await dB.get_key("PHUB_POST_DB")

    await callback.edit_message_text(
        f"{callback.message.text.html}\n\n<i>Fetching details{' and creating a new channel for this post' if not chat_id else ''}...</i>"
    )

    if not manga_name and not post_id:
        manga_name = await PS.get_title(manga_url)

    if post_id:
        post = next(
            p for p in post_db.get("posts", []) if p.get("message_id") == post_id
        )
        post_title = [name.strip() for name in post["title"].split("|")]
        post_chat = post["fchannel"].get("chat_id")
        post_image = (
            await client.get_messages(post_db["channel_id"], post["message_id"])
        ).photo.file_id
        psub = await anext(pdB.all_subs({"chat": post_chat}), {})
        chat_id = chat_id or post["fchannel"].get("new_chat_id")

    al_id = post.get("al_id") if post else None
    if not al_id:
        al_search = (
            await ani.searchanilist(post_title[0] if post else manga_name, manga=True)
        )[0]
        re_search = False
        if post and len(post_title) > 1:
            if not al_search:
                al_search = (await ani.searchanilist(post_title[-1], manga=True))[0]
            else:
                re_search = True

        _, al_search_res = await ask_callback_options(
            callback.message,
            f"{callback.message.text.html}\n\n<b>Confirm this manga's AL ID for me amongst these below:</b>",
            (
                [
                    *[
                        (
                            search_item["title"]["english"]
                            or search_item["title"]["romaji"],
                            search_item["id"],
                        )
                        for search_item in al_search
                    ],
                    "N/A",
                    "Search Name (Provide)",
                ]
                + (["Search Again (2nd Name)"] if re_search else [])
            ),
            user_id=callback.from_user.id,
            split=1,
            edit=True,
        )

        if al_search_res.startswith("Search"):
            sa_name = None
            if al_search_res.startswith("Search Name"):
                _, sa_response = await ask_message(
                    callback.message,
                    f"{callback.message.text.html}\n\n<b>Okay! Reply back to me with the name you want to search in AL for.</b>",
                    filters=(
                        filters.chat(callback.message.chat.id)
                        & filters.user(callback.from_user.id)
                        & filters.text
                    ),
                    timeout=5 * 60,
                    edit=True,
                )
                sa_name = sa_response.text.strip()
            al_search = (
                await ani.searchanilist(sa_name or post_title[-1], manga=True)
            )[0]
            _, al_search_res = await ask_callback_options(
                callback.message,
                f"{callback.message.text.html}\n\n<b>Let's retry, confirm this manga's AL ID for me amongst these below:</b>",
                [
                    *[
                        (
                            search_item["title"]["english"]
                            or search_item["title"]["romaji"],
                            search_item["id"],
                        )
                        for search_item in al_search
                    ],
                    "N/A",
                ],
                user_id=callback.from_user.id,
                split=1,
                edit=True,
            )

        al_id = al_search_res if al_search_res != "N/A" else None
        if al_id and post:
            post["al_id"] = al_id
            await dB.update_one(
                {"PHUB_POST_DB.posts.message_id": post["message_id"]},
                {"$set": {"PHUB_POST_DB.posts.$.al_id": al_id}},
            )
        await callback.edit_message_text(
            f"{callback.message.text.html}\n\n<i>Done! Now doing post processing...</i>"
        )

    if al_id:
        caption, image, markup, manga_json = await ani.get_anime_manga(
            None, "anime_manga", al_id, re_json=True
        )
        if post:
            post["al_id"] = al_id
            post["rating"] = manga_json["averageScore"]

    if not chat_id:
        create_channel = await client.ub.create_channel(
            post_title[0] if post else manga_name, bio_for_channel[0].text
        )
        self_member = await create_channel.get_member("me")
        await create_channel.promote_member(
            client.me.id, privileges=self_member.privileges
        )
        chat_id = create_channel.id
        bulkp_opts["chat_id"]["value"] = chat_id
        if post:
            post["fchannel"]["new_chat_id"] = chat_id
            await dB.update_one(
                {"PHUB_POST_DB.posts.message_id": post["message_id"]},
                {"$set": {"PHUB_POST_DB.posts.$.fchannel.new_chat_id": chat_id}},
            )
        callback.message = await callback.edit_message_text(
            f"{callback.message.text.html}\n<b>››Chat ID:</b> <code>{chat_id}</code>"
        )
        await asyncio.sleep(1)
        await (await client.ub.send_message(chat_id, "test")).delete()
        await callback.edit_message_text(
            f"{callback.message.text.html}\n\n<i>Done! Now doing post processing...</i>"
        )

    if chat_pic:
        if is_url(chat_pic):
            chat_pic = (await AioHttp.download(chat_pic))[0]
        if not os.path.exists(chat_pic):
            chat_pic = ""
    elif post:
        chat_pic = post_image
    elif al_id:
        chat_pic = manga_json["coverImage"]["extraLarge"]

    Chat = await client.get_chat(chat_id)
    if not Chat.photo and chat_pic:
        await client.set_chat_photo(chat_id, photo=chat_pic)
    if Chat.description != bio_for_channel[0].text:
        await client.set_chat_description(chat_id, bio_for_channel[0].text)

    if post:
        post["fchannel"]["chat_id"] = chat_id
        post["fchannel"]["invite_link"] = await get_chat_invite_link(chat_id)

    if al_id:
        temp_img = (await AioHttp.download(image, filename=f"cache/{al_id}.png"))[0]
        is_nsfw = False
        try:
            nsfw_scan = await safone_api.nsfw_scan(file=temp_img)
            is_nsfw = nsfw_scan.data.is_nsfw
        except Exception as e:
            LOGGER(__name__).info(f"SafoneAPI.nsfw_scan error: {e}")
        if not is_nsfw:
            first_msg = await client.send_photo(
                chat_id, temp_img, caption=caption, reply_markup=markup
            )
        else:
            first_msg = await client.send_message(chat_id, caption, reply_markup=markup)
        await client.send_cached_media(chat_id, first_msg_media)
        os.remove(temp_img)
    elif post:
        first_msg_text = ani.make_pmanga_text(
            post["title"],
            post["rating"],
            post["status"],
            post["chapters"],
            post["genres"],
            link=post["fchannel"]["invite_link"],
        )
        first_msg = await client.send_photo(
            chat_id, chat_pic or post_image, caption=first_msg_text
        )
        await client.send_cached_media(chat_id, first_msg_media)
    else:
        _, to_be_first_msg = await ask_message(
            callback.message,
            f"{callback.message.text.html}\n\n<b>Since this is not on AniList, Make a post in the same format as the other posts on Pornhwa Hub and send it here.</b>",
            from_user=callback.from_user.id,
            filters=filters.chat(callback.message.chat.id)
            & filters.user(callback.from_user.id)
            & filters.photo
            & filters.caption,
            timeout=10 * 60,
            edit=True,
        )
        first_msg = await client.copy_message(
            chat_id, to_be_first_msg.chat.id, to_be_first_msg.id
        )
        await client.send_cached_media(chat_id, first_msg_media)
        title, rating, status, chapter, genres, _ = parse_message_caption(
            first_msg.caption
        )
        post = {
            "title": title,
            "rating": rating,
            "status": status,
            "chapters": chapter,
            "genres": genres,
            "fchannel": {
                "invite_link": await get_chat_invite_link(chat_id),
                "chat_id": chat_id,
                "first_msg_id": first_msg.id,
            },
        }
        await callback.edit_message_text(
            f"{callback.message.text.html}\n\n<i>Got it! Continuing the processs...</i>"
        )

    await (await first_msg.pin(disable_notification=True)).delete()

    if bulkp_opts["pdf_pass"].get("value") and not bulkp_opts["showpass"].get("value"):
        password_msg = await client.send_message(
            chat_id,
            f'<b>Password for PDFs =</b> <code>{bulkp_opts["pdf_pass"].get("value")}</code>',
        )
        await (await password_msg.pin(disable_notification=True)).delete()
        if post:
            post["fchannel"]["password_msg_id"] = password_msg.id

    if post:
        post["fchannel"]["first_msg_id"] = first_msg.id

    bulk_id = f"cancel_bulk:{callback.from_user.id}:{get_random_id()}"

    try:
        arg, kwargs = get_function_args(process_bulk)
        result = await process_bulk(
            link=manga_url,
            chat_id=chat_id,
            name=post_title[0] if post_id else manga_name,
            **{
                option: option_info["value"]
                for option, option_info in bulkp_opts.items()
                if option in kwargs and option_info.get("value")
            },
            thumb="bot/resources/phub_files_thumb.png",
            bulk_id=bulk_id,
            status=callback.message,
            status_text=callback.message.text.html,
        )
        if result is None:
            return
    finally:
        if bulk_id in BULK_PROCESS:
            BULK_PROCESS.remove(bulk_id)

    last_sent_ch, status = result

    if post:
        post["chapters"] = str(int(float(last_sent_ch)))

    is_finished = post["status"].lower() == "finished" if post else None
    if not is_finished and al_id and manga_json["status"] == "FINISHED":
        is_finished = True
        if str(manga_json["chapters"]) not in [
            str(int(float(last_sent_ch))),
            str(int(float(last_sent_ch)) + 1) if "." in last_sent_ch else None,
        ]:
            _, is_finished = await ask_callback_options(
                callback.message,
                f"<b>Not sure whether this manga is finished or not. Please confirm it for me.</b>",
                ["Yeah, it's Finished.", "No, it's not."],
                user_id=callback.from_user.id,
                split=1,
                quote=True,
            )
            await _.delete()
            is_finished = is_finished.startswith("Yeah")
            await callback.edit_message_text(
                f"{callback.message.text.html}\n\n<i>Got it! Continuing the processs...</i>"
            )

    if is_finished:
        if post:
            post["status"] = "Finished"
        await client.copy_message(chat_id, data_source_chat, data_ids[0])
        await client.copy_message(chat_id, data_source_chat, data_ids[1])

    if al_id and not post_id:
        post = {
            "title": manga_name,
            "rating": manga_json["averageScore"],
            "status": manga_json["status"].title() if is_finished else "Releasing",
            "chapters": str(int(float(last_sent_ch))),
            "genres": manga_json["genres"],
            "fchannel": {
                "invite_link": await get_chat_invite_link(chat_id),
                "chat_id": chat_id,
                "first_msg_id": first_msg.id,
                **(
                    {"password_msg_id": password_msg.id}
                    if bulkp_opts["pdf_pass"].get("value")
                    and not bulkp_opts["showpass"].get("value")
                    else {}
                ),
            },
            "al_id": al_id,
        }
        phub_post = await client.send_photo(
            post_db["channel_id"],
            chat_pic or manga_json["coverImage"]["extraLarge"],
            caption=ani.make_pmanga_text(
                post["title"],
                post["rating"],
                post["status"],
                post["chapters"],
                post["genres"],
                link=post["fchannel"]["invite_link"],
            ),
        )
        post = {"message_id": phub_post.id, **post}
        await dB.update_one(
            {"PHUB_POST_DB": {"$exists": 1}}, {"$push": {"PHUB_POST_DB.posts": post}}
        )
        if post["status"].lower() == "releasing":
            lc = await pdB.get_lc(psub_url or manga_url)
            if not lc:
                lc_url = (await anext(PS.iter_chapters(psub_url or manga_url)))[1]
                await pdB.add_lc(psub_url or manga_url, lc_url)
            await pdB.add_sub(
                PS.guess_ps(psub_url or manga_url),
                psub_url or manga_url,
                post["fchannel"]["chat_id"],
                manga_name,
                send_updates=True,
                file_mode="PDF",
                file_pass=bulkp_opts["pdf_pass"].get("value"),
            )
        await callback.edit_message_text(
            f"{callback.message.text.html}\n\n<b>Process Completed! [Post]({phub_post.link.replace('-100', '')}) sent in Pornhwa Hub.</b>",
            disable_web_page_preview=True,
        )
    elif post_id:
        try:
            phub_post = await client.edit_message_caption(
                post_db["channel_id"],
                post["message_id"],
                caption=ani.make_pmanga_text(
                    post["title"],
                    post["rating"],
                    post["status"],
                    post["chapters"],
                    post["genres"],
                    link=post["fchannel"]["invite_link"],
                ),
            )
        except MessageNotModified:
            pass
        if psub:
            if psub_url:
                psub["url"] = psub_url
            if file_pass := bulkp_opts["pdf_pass"].get("value"):
                psub["file_pass"] = file_pass
            psub["chat"] = chat_id
            await pdB.update_one({"_id": psub["_id"]}, {"$set": psub})
        post["fchannel"].pop("new_chat_id", None)
        await dB.update_key("PHUB_POST_DB", post_db)
        if post_chat:
            with suppress(Exception):
                await client.ub.leave_chat(post_chat)
        await callback.edit_message_text(
            f"{callback.message.text.html}\n\n<b>Process Completed! Edited the [post](https://t.me/c/{str(post_db['channel_id']).replace('-100', '')}/{post['message_id']}) in Pornhwa Hub.</b>",
            disable_web_page_preview=True,
        )
    else:
        phub_post = await client.copy_message(
            post_db["channel_id"],
            first_msg.chat.id,
            first_msg.id,
            caption=ani.make_pmanga_text(
                post["title"],
                post["rating"],
                post["status"],
                post["chapters"],
                post["genres"],
                link=post["fchannel"]["invite_link"],
            ),
        )
        post = {"message_id": phub_post.id, **post}
        await dB.update_one(
            {"PHUB_POST_DB": {"$exists": 1}}, {"$push": {"PHUB_POST_DB.posts": post}}
        )
        if post["status"].lower() == "releasing":
            lc = await pdB.get_lc(psub_url or manga_url)
            if not lc:
                lc_url = (await anext(PS.iter_chapters(psub_url or manga_url)))[1]
                await pdB.add_lc(psub_url or manga_url, lc_url)
            await pdB.add_sub(
                PS.guess_ps(psub_url or manga_url),
                psub_url or manga_url,
                post["fchannel"]["chat_id"],
                manga_name,
                send_updates=True,
                file_mode="PDF",
                file_pass=bulkp_opts["pdf_pass"].get("value"),
            )

        await callback.edit_message_text(
            f"{callback.message.text.html}\n\n<b>Process Completed! [Post]({phub_post.link.replace('-100', '')}) sent in Pornhwa Hub.</b>",
            disable_web_page_preview=True,
        )

    if os.path.exists(chat_pic):
        os.remove(chat_pic)
