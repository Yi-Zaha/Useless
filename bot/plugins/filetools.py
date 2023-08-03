import asyncio
import glob
import os
import re
import time
from datetime import datetime

from pyrogram import filters

from bot import ALLOWED_USERS, SUDOS, bot
from bot.helpers.progress_cb import Stream, progress_cb
from bot.utils.aiohttp_helper import AioHttp, get_name_and_size_from_response
from bot.utils.media import get_video_duration, get_video_ss
from bot.utils.pdf import get_image_size


def get_ss_and_duration(video_path: str):
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


async def send_media(media_type, chat, file, message=None, progress=progress_cb, **kwargs):
    c_time = time.time()
    file_name = kwargs.get("file_name", None)
    if file_name is None:
        file_name = os.path.basename(str(file))
    if media_type in ("vid", "video"):
        ss, duration, width, height = get_ss_and_duration(file)
        duration = kwargs.pop("duration", duration)
        width = kwargs.pop("width", width)
        height = kwargs.pop("height", height)
        thumb = kwargs.pop("thumb") or ss
        await bot.send_video(
            chat,
            file,
            thumb=thumb,
            width=width,
            height=height,
            duration=duration,
            progress=progress,
            progress_args=(
                message,
                c_time,
                "Uploading...",
                file_name,
            ),
            **kwargs,
        )
        if ss and os.path.exists(ss):
            os.remove(ss)

    elif media_type in ("pic", "photo"):
        await bot.send_photo(
            chat,
            file,
            progress=progress,
            progress_args=(
                message,
                c_time,
                "Uploading...",
                file_name,
            ),
            **kwargs,
        )

    elif media_type in ("audio"):
        await bot.send_audio(
            chat,
            file,
            progress=progress,
            progress_args=(
                message,
                c_time,
                "Uploading...",
                file_name,
            ),
            **kwargs,
        )

    elif media_type in ("gif", "animation"):
        await bot.send_animation(
            chat,
            file,
            progress=progress,
            progress_args=(
                message,
                c_time,
                "Uploading...",
                file_name,
            ),
            **kwargs,
        )
    else:
        await bot.send_document(
            chat,
            file,
            progress=progress,
            progress_args=(
                message,
                c_time,
                "Uploading...",
                file_name,
            ),
            **kwargs,
        )


@bot.on_message(filters.command(["download", "dl"]) & filters.user(SUDOS))
async def media_download(client, message):
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
                file_name=input_text,
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
async def media_upload(client, message):
    status = await message.reply("Processing..")
    command = message.text.split(" ")
    if len(command) == 1:
        return await status.edit("You have to provide a file path in order to upload.")

    media_type = (
        command[0].split("_")[-1] if len(command[0].split("_")) > 1 else "document"
    )
    text = " ".join(command[1:])
    thumb = "thumb.jpg" if "-t" in text else None
    "-f" in text
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
            text, chat = map(str.strip, text.split("|"))
            chat = int(chat)
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
        try:
            await send_media(
                media_type,
                chat,
                file,
                message=status,
                thumb=thumb,
                caption=caption,
                protect_content=protect_content,
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


@bot.on_message(filters.regex(r"^/rename ?(.*)") & filters.user(ALLOWED_USERS))
async def media_rename(client, message):
    reply = message.reply_to_message
    command = message.text.split(" ")
    if not (getattr(reply, "media", None) or len(command) > 1):
        return await message.reply(
            "Reply to a media and provide a file name to rename."
        )

    status = await message.reply("Processing...")
    media = getattr(reply, reply.media._value_)
    media_type = command[0].split("_")
    media_type = media_type[1] if len(media_type) > 1 else reply.media._value_
    flags = ("-f", "-t", "-nt", "-protect")
    force_doc, thumb, no_thumb, protect_content = (
        flags[0] in message.text,
        flags[1] in message.text,
        flags[2] in message.text,
        flags[3] in message.text,
    )
    thumb = "thumb.jpg" if thumb else None
    extra_args = {}
    if not thumb and media.thumbs:
        thumb = await client.download_media(media.thumbs[-1].file_id)
        if media_type in ("vid", "video") and reply.video:
            extra_args.update(
                {
                    "duration": media.duration,
                    "height": media.thumbs[-1].height,
                    "width": media.thumbs[-1].width,
                }
            )
    if no_thumb:
        thumb = None

    for cmd in command[:-1]:
        for flag in flags:
            if flag in cmd:
                command.remove(cmd)

    file_name = media.file_name
    output_name = " ".join(command[1:])
    chat_id = message.chat.id
    if "|" in output_name:
        try:
            output_name, chat_id = map(str.strip, output_name.split("|"))
            chat_id = int(chat_id)
        except ValueError:
            pass

    start_time = datetime.now()
    
    downloaded_file = await reply.download(
        file_name="downloads/",
        progress=progress_cb,
        progress_args=(status, time.time(), "Downloading...", file_name),
    )
    try:
        await send_media(
            media_type,
            chat_id,
            downloaded_file,
            file_name=output_name,
            caption=f"<code>{output_name}</code>",
            message=status,
            thumb=thumb,
            protect_content=protect_content,
            **extra_args,
        )
    except Exception as e:
        return await status.edit(
            f"<b>Oops! Something went wrong.</b>\n\n<code>{type(e).__name__}: {e}</code>"
        )

    end_time = datetime.now()
    time_taken = (end_time - start_time).seconds
    success_text = f"Renamed <code>{file_name}</code> to <code>{output_name}</code> in <code>{time_taken}</code> seconds"
    if chat_id != message.chat.id:
        success_text += f" and sent to chat ID <code>{chat_id}</code>"
    success_text += "."
    await status.edit(success_text)

    if thumb and thumb != "thumb.jpg":
        os.remove(thumb)
    os.remove(downloaded_file)


"""
async def media_rename(client, message):
    reply = message.reply_to_message
    if not (getattr(reply, "media", False) or len(message.command) == 1):
        return await message.reply(
            "Reply to a media and provide a file name to rename."
        )

    status = await message.reply("Processing...")
    media = getattr(reply, reply.media._value_)
    command = message.text.split(" ")
    media_type = command[0].split("_")
    media_type = media_type[1] if len(media_type) > 1 else reply.media._value_
    force_doc, thumb, no_thumb, protect_content = (
        flags[0] in message.text,
        flags[1] in message.text,
        flags[2] in message.text,
        flags[3] in message.text,
    )
    thumb = "thumb.jpg" if thumb else None
    extra_args = {}
    if not thumb and media.thumbs:
        thumb = await client.download_media(media.thumbs[-1].file_id)
        if media_type in ("vid", "video") and reply.video:
            extra_args.update(
                {
                    "duration": media.duration,
                    "height": media.thumbs[-1].height,
                    "width": media.thumbs[-1].width,
                }
            )
    if no_thumb:
        thumb = None
    for cmd in command[:-1]:
        for flag in flags:
            if flag in cmd:
                command.remove(cmd)

    file_name = media.file_name
    output_name = " ".join(command[1:])
    chat_id = message.chat.id
    if "|" in output_name:
        try:
            output_name, chat_id = map(str.strip, output_name.split("|"))
            chat_id = int(chat_id)
        except ValueError:
            pass

    start_time = datetime.now()

    stream = Stream(
        name=output_name, file_size=media.file_size, stream=client.stream_media(reply)
    )
    await stream.fill()
    await send_media(
        media_type,
        chat_id,
        stream,
        message=status,
        progress=stream.progress,
        thumb=thumb,
        caption=f"<code>{output_name}</code>",
        protect_content=protect_content,
        **extra_args,
    )

    end_time = datetime.now()
    time_taken = (end_time - start_time).seconds
    success_text = f"Renamed <code>{file_name}</code> to <code>{output_name}</code> in <code>{time_taken}</code> seconds"
    if chat_id != message.chat.id:
        success_text += f" and sent to chat ID <code>{chat_id}</code>"
    success_text += "."
    await status.edit(success_text)

    if thumb and thumb != "thumb.jpg":
        os.remove(thumb)
"""