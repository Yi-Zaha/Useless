import asyncio
import glob
import os
import re
import time
from datetime import datetime

from pyrogram import filters

from bot import SUDOS, bot
from bot.helpers.progress_cb import progress_cb
from bot.utils.aiohttp_helper import AioHttp, get_name_and_size_from_response
from bot.utils.media import get_video_duration, get_video_ss
from bot.utils.pdf import get_image_size


@bot.on_message(filters.command(["download", "dl"]) & filters.user(SUDOS))
async def download_media(client, message):
    status = await message.reply("Processing...")
    input_text = " ".join(message.command[1:]) if len(message.command) > 1 else ""
    reply = message.reply_to_message
    start_time = datetime.now()

    if reply and reply.media:
        media_object = getattr(reply, reply.media._value_, None)
        file_name = (
            getattr(media_object, "file_name", None)
            if not input_text or input_text.endswith("/")
            else input_text.strip()
        )
        c_time = time.time()
        try:
            downloaded_path = await reply.download(
                file_name=file_name,
                progress=progress_cb,
                progress_args=(status, c_time, "Downloading...", file_name),
            )
            end_time = datetime.now()
            time_taken = (end_time - start_time).seconds
            await status.edit(
                f"Downloaded to <code>{downloaded_path}</code> in <code>{time_taken}</code> seconds."
            )
        except Exception as e:
            await status.edit(
                f"<b>Oops! Something went wrong.</b>\n\n<code>{e.__class__.__name__}: {e}</code>"
            )
    elif input_text:
        try:
            if "|" in input_text:
                dl_url, file_path = map(str.strip, input_text.split("|"))
                if "/" not in file_path:
                    os.makedirs("downloads", exist_ok=True)
                    file_path = os.path.join("downloads", file_path)
            else:
                os.makedirs("downloads", exist_ok=True)
                dl_url = input_text.strip()
                response = await AioHttp.request(dl_url, re_res=True)
                file_name, _ = get_name_and_size_from_response(response)
                file_path = os.path.join("downloads", file_name)

            c_time = time.time()
            downloaded_path, _, _ = await AioHttp.download(
                dl_url,
                file_path,
                progress_callback=lambda d, t: asyncio.create_task(
                    progress_cb(
                        d,
                        t,
                        status,
                        c_time,
                        f"Downloading Url - {dl_url}",
                        file_path,
                        True,
                    )
                ),
            )
            end_time = datetime.now()
            time_taken = (end_time - start_time).seconds
            await status.edit(
                f"Downloaded Url <code>{dl_url}</code> to <code>{downloaded_path}</code> in <code>{time_taken}</code> seconds."
            )
        except Exception as e:
            await status.edit(
                f"<b>Oops! Something went wrong.</b>\n\n<code>{e.__class__.__name__}: {e}</code>"
            )
    else:
        await status.edit("Reply to media or provide a URL to download.")


@bot.on_message(filters.regex(r"^/(upload|ul) ?(.*)", re.I) & filters.user(SUDOS))
async def upload_media(client, message):
    status = await message.reply("Processing..")
    command = message.text.split(" ")
    if len(command) == 1:
        return await status.edit("You have to provide file path in order to upload.")

    media_type = command[0].split("_")
    media_type = media_type[-1] if len(media_type) > 1 else "document"
    text = " ".join(command[1:])
    thumb = "thumb.jpg" if "-t" in text else None
    force_doc = "-f" in text
    protect_content = "-protect" in text

    flags = ("-f", "-t", "-protect")
    for flag in flags:
        for cmd in command[:-1]:
            if flag in cmd:
                command.remove(cmd)

    text = " ".join(command[1:])
    chat = message.chat.id
    if "|" in text:
        try:
            chat = int(text.split("|")[-1].strip())
        except ValueError:
            pass

    text += "*" if text.endswith("/") else ""
    files = glob.glob(text)

    if not files and os.path.exists(text):
        files = [text]

    if not files and not os.path.exists(text):
        return await status.edit("File doesn't exist.")

    start_time = datetime.now()
    for file in files:
        if os.path.isdir(file):
            continue
        caption = f"<code>{os.path.basename(file)}</code>"
        c_time = time.time()
        try:
            if media_type in ("vid", "video"):
                ss, duration, width, height = _get_ss_and_duration(file)
                await client.send_video(
                    chat,
                    file,
                    thumb=thumb or ss,
                    caption=caption,
                    width=width,
                    height=height,
                    protect_content=protect_content,
                    duration=duration,
                    progress=progress_cb,
                    progress_args=(status, c_time, "Uploading...", file),
                )
                if ss and os.path.exists(ss):
                    os.remove(ss)

            elif media_type in ("pic", "photo"):
                await client.send_photo(
                    chat,
                    file,
                    caption=caption,
                    protect_content=protect_content,
                    progress=progress_cb,
                    progress_args=(status, c_time, "Uploading...", file),
                )

            elif media_type in ("audio"):
                await client.send_audio(
                    chat,
                    file,
                    caption=caption,
                    thumb=thumb,
                    protect_content=protect_content,
                    progress=progress_cb,
                    progress_args=(status, c_time, "Uploading...", file),
                )

            elif media_type in ("gif", "animation"):
                await client.send_animation(
                    chat,
                    file,
                    caption=caption,
                    thumb=thumb,
                    protect_content=protect_content,
                    progress=progress_cb,
                    progress_args=(status, c_time, "Uploading...", file),
                )
            else:
                await client.send_document(
                    chat,
                    file,
                    caption=caption,
                    thumb=thumb,
                    force_document=force_doc,
                    protect_content=protect_content,
                    progress=progress_cb,
                    progress_args=(status, c_time, "Uploading...", file),
                )

        except Exception as e:
            return await status.edit(
                f"<b>Oops! Something went wrong.</b>\n\n<code>{e.__class__.__name__}: {e}</code>"
            )
    end_time = datetime.now()
    time_taken = (end_time - start_time).seconds
    if message.chat.id == chat:
        await status.edit(
            f"Uploaded <code>{text}</code> in <code>{time_taken}</code> seconds."
        )
    else:
        await status.edit(
            f"Uploaded <code>{text}</code> to <code>{chat}</code> in <code>{time_taken}</code> seconds."
        )


def _get_ss_and_duration(video_path: str):
    thumb, duration, width, height = None, 0, 0, 0
    try:
        thumb = get_video_ss(video_path)
    except BaseException:
        pass
    try:
        duration = get_video_duration(video_path)
    except BaseException:
        pass
    try:
        width, height = get_image_size(thumb)
    except BaseException:
        pass
    return thumb, duration, width, height
