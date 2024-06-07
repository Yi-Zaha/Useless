import asyncio
import re
import string

from pyrogram import Client, filters, types

from bot import PHUB_CHANNEL, SUDOS
from bot.config import Config
from bot.helpers import ani
from bot.logger import LOGGER
from bot.utils.db import dB
from bot.utils.functions import get_chat_messages, get_latest_chat_msg

INDEX_CHANNEL = Config.get("PORNHWA_HUB_INDEX", -1001749847496)
UPDATING_INDEX = False


@Client.on_message(filters.command("updateindex") & filters.user(SUDOS))
async def update_index(client, message):
    status = await message.reply("Processing...")
    try:
        await update_phub_index(client)
        await status.edit("Successfully updated the PH Index.")
    except Exception:
        LOGGER(__name__).info("Error raised in updating PH Index", exc_info=True)
        await status.edit("Updating PH Index raised some errors (Check Logs).")


@Client.on_message(filters.chat(PHUB_CHANNEL))
async def on_phub_handler(client, message):
    await dB.update_key("PH_LAST_ID", message.id + 1, upsert=True)
    try:
        await update_phub_index(client)
    except Exception:
        LOGGER(__name__).info("Error raised in updating PH Index", exc_info=True)


@Clinet.on_join_chat_request(filters.chat(PHUB_CHANNEL))
async def phub_join_requests(client, request):
    await request.approve()


async def update_phub_index(client):
    global UPDATING_INDEX
    if UPDATING_INDEX:
        return

    UPDATING_INDEX = True

    index_posts = await get_chat_messages(
        INDEX_CHANNEL, first_msg_id=62, last_msg_id=89
    )
    index = {"#": {}, **{alpha: {} for alpha in string.ascii_uppercase}}
    namelinks = {}
    posts = {}
    post_db = await dB.get_key("PHUB_POST_DB")

    messages = await get_chat_messages(
        PHUB_CHANNEL,
        first_msg_id=7,
        last_msg_id=await get_latest_chat_msg(PHUB_CHANNEL) + 1,
        sleep_for_flood=10,
    )

    for message in messages:
        if "→Status:" in str(message.caption):
            name, rating, status, chapters_count, genres, invite_link = (
                parse_message_caption(message.caption, message.caption_entities)
            )
            chat_id = str(message.chat.id).replace("-100", "")
            link = f"https://t.me/c/{chat_id}/{message.id}"

            index_key = name[0] if name[0].isalpha() else "#"
            tick = get_status_tick(status)

            i_text = f'{tick} <a href="{link}">{name}</a>\n'
            index[index_key][name] = i_text
            namelinks[name] = link

            post_info = {
                "message_id": message.id,
                "title": name,
                "rating": rating,
                "status": status,
                "chapters": chapters_count,
                "genres": genres,
                "fchannel": {"invite_link": invite_link},
            }

            await update_post_db(client, post_db, post_info)

    for f in sorted(index):
        texts = index[f]
        if f not in posts:
            posts[f] = f"<b>🔖{f} Section</b>\n\n"
            for name in sorted(texts):
                text = texts[name]
                posts[f] += text

    await update_index_posts(index_posts, posts)

    await dB.update_key("PHUB_NAMELINKS", namelinks, upsert=True)
    await dB.update_key("PHUB_POST_DB", post_db, upsert=True)
    UPDATING_INDEX = False


def parse_message_caption(caption, entities=None):
    name = caption.splitlines()[0].replace("─=≡", "").replace("≡=─", "").strip()
    rating = re.search(r"Rating: (.*)", caption).group(1)
    status = re.search(r"Status: (.*)", caption).group(1).strip()
    chapters_count = (
        re.search(r"Chapters: (.*)", caption).group(1).strip().replace("+", "")
    )
    genres = re.search(r"Genres: (.*)", caption).group(1).split(", ")
    invite_link = None
    if entities:
        invite_link = [entity.url for entity in entities if entity.url][-1]
    return name, rating, status, chapters_count, genres, invite_link


def get_status_tick(status):
    if status.lower() == "releasing":
        return "🔷"
    elif status.lower() == "finished":
        return "🔶"
    elif status.lower() == "incomplete":
        return "♦️"


async def update_post_db(client, post_db, post_info):
    _index = next(
        (
            n
            for n, item in enumerate(post_db["posts"])
            if item["message_id"] == post_info["message_id"]
        ),
        None,
    )
    if _index is not None:
        # Update existing post
        if (
            post_db["posts"][_index]["status"].lower() == "releasing"
            and post_info["status"].lower() != "finished"
        ):
            if (
                post_info["status"].lower() == "releasing"
                and post_info["fchannel"]["invite_link"]
                != post_db["posts"][_index]["fchannel"]["invite_link"]
            ):
                if post_chat := await get_chat_by_invite_link(
                    post_info["fchannel"]["invite_link"]
                ):
                    post_info["fchannel"]["chat_id"] = post_chat.id
                else:
                    post_db["posts"][_index]["fchannel"].pop("chat_id", None)

            if float(post_db["posts"][_index]["chapters"]) > float(
                post_info["chapters"]
            ):
                post_info["chapters"] = post_db["posts"][_index]["chapters"]
                if al_id := post_db["posts"][_index].get("al_id"):
                    # Update rating and status if manga is finished
                    manga_json = (
                        await ani.anime_json_synomsis(ani.manga_query, {"id": al_id})
                    )["data"]["Media"]
                    post_info["rating"] = manga_json["averageScore"]
                    if manga_json["status"] == "FINISHED" and str(
                        manga_json["chapters"]
                    ) in [
                        str(int(float(post_db["posts"][_index]["chapters"]))),
                        (
                            str(int(float(post_db["posts"][_index]["chapters"])) + 1)
                            if "." in post_db["posts"][_index]["chapters"]
                            else None
                        ),
                    ]:
                        await client.copy_message(
                            post_db["posts"][_index]["fchannel"]["chat_id"],
                            -1001783376856,
                            37423,
                        )
                        await client.copy_message(
                            post_db["posts"][_index]["fchannel"]["chat_id"],
                            -1001783376856,
                            37424,
                        )
                        post_info["status"] = "Finished"
                await client.edit_message_caption(
                    post_db["channel_id"],
                    post_info["message_id"],
                    ani.make_pmanga_text(
                        post_info["title"],
                        post_info["rating"],
                        post_info["status"],
                        post_info["chapters"],
                        post_info["genres"],
                        link=post_info["fchannel"]["invite_link"],
                    ),
                )
        post_db["posts"][_index].setdefault("fchannel", {}).update(
            post_info.pop("fchannel")
        )
        post_db["posts"][_index].update(post_info)
    else:
        # Add new post to the database
        post_db["posts"].append(post_info)


async def get_chat_by_invite_link(client, invite_link):
    if not client.ub:
        return
    invite_link = invite_link if ".me/+" in invite_link else invite_link.split("/")[-1]
    try:
        chat = await client.ub.get_chat(invite_link)
        if isinstance(chat, types.ChatPreview):
            chat = await client.ub.join_chat(invite_link)
    except Exception as e:
        LOGGER(__name__).error(
            f"[UB] Error getting chat by invite link [{invite_link}]: {e}"
        )
        return None

    return chat


async def update_index_posts(index_posts, posts):
    for index_post, post_text in zip(index_posts, posts.values()):
        if not post_text or index_post.text.html == post_text:
            continue

        try:
            await index_post.edit(post_text)
        except Exception as e:
            print(f"Error in updating PH Index post id {index_post.id}: {e}")
        await asyncio.sleep(2)
