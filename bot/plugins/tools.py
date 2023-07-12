import glob
import os

from html_telegraph_poster.upload_images import upload_image
from pyrogram import errors, filters
from pyrogram.enums import ChatAction, ParseMode

from bot import ALLOWED_USERS, SUDOS, bot
from bot.logger import LOG_FILE
from bot.utils.db import dB
from bot.utils.functions import humanbytes as hb


@bot.on_message(filters.command("restart") & filters.user(ALLOWED_USERS))
async def restart(client, message):
    await message.reply("Updating and rebooting...")
    await bot.reboot()


@bot.on_message(filters.command("logs") & filters.user(ALLOWED_USERS))
async def send_logs(client, message):
    await client.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
    await message.reply_document(LOG_FILE)
    await client.send_chat_action(message.chat.id, ChatAction.CANCEL)


@bot.on_message(filters.command("noformat") & filters.user(ALLOWED_USERS))
async def noformat_text(client, message):
    if not message.reply_to_message or not message.reply_to_message.text:
        return await message.reply("Reply to a text")
    await message.reply(
        f"<code>{message.reply_to_message.text.markdown}</code>",
        parse_mode=ParseMode.HTML,
    )


@bot.on_message(
    filters.command(["setthumb", "thumbnail", "thumb"]) & filters.user(SUDOS)
)
async def set_thumbnail(client, message):
    reply = message.reply_to_message
    if getattr(reply, "photo", None):
        file = await reply.download("./thumb.jpg")

    elif getattr(reply, "document", None) and reply.document.thumbs:
        file = await client.download_media(
            reply.document.thumbs[-1].file_id, file_name="./thumb.jpg"
        )
    else:
        return await message.reply(
            "Reply to a photo or a document with thumb to set default thumbnail."
        )

    thumb_url = upload_image(file)
    await dB.set_key("THUMBNAIL", thumb_url)
    await message.reply("Default thumbnail set!")


@bot.on_message(filters.command("ls") & filters.user(SUDOS))
async def list_directory(client, message):
    if len(message.command) < 2:
        files = "*"
    else:
        files = message.command[1]
        if files.endswith("/"):
            files += "*"
        elif "*" not in files:
            files += "/*"
    files = glob.glob(files)
    if not files:
        return await message.reply_text("`Directory Empty or Incorrect.`")

    pyfiles = []
    jsons = []
    vdos = []
    audios = []
    pics = []
    others = []
    otherfiles = []
    folders = []
    text = []
    apk = []
    exe = []
    zip_ = []
    book = []

    for file in sorted(files):
        if os.path.isdir(file):
            folders.append("📂 " + str(file))
        elif file.endswith(".py"):
            pyfiles.append("🐍 " + str(file))
        elif file.endswith(".json"):
            jsons.append("🔮 " + str(file))
        elif file.endswith((".mkv", ".mp4", ".avi", ".gif", "webm")):
            vdos.append("🎥 " + str(file))
        elif file.endswith((".mp3", ".ogg", ".m4a", ".opus")):
            audios.append("🔊 " + str(file))
        elif file.endswith((".jpg", ".jpeg", ".png", ".webp", ".ico")):
            pics.append("🖼 " + str(file))
        elif file.endswith((".txt", ".text", ".log")):
            text.append("📄 " + str(file))
        elif file.endswith((".apk", ".xapk")):
            apk.append("📲 " + str(file))
        elif file.endswith((".exe", ".iso")):
            exe.append("⚙ " + str(file))
        elif file.endswith((".zip", ".rar")):
            zip_.append("🗜 " + str(file))
        elif file.endswith((".pdf", ".epub")):
            book.append("📗 " + str(file))
        elif "." in file[1:]:
            others.append("🏷 " + str(file))
        else:
            otherfiles.append("📒 " + str(file))

    omk = [
        *sorted(folders),
        *sorted(pyfiles),
        *sorted(jsons),
        *sorted(zip_),
        *sorted(vdos),
        *sorted(pics),
        *sorted(audios),
        *sorted(apk),
        *sorted(exe),
        *sorted(book),
        *sorted(text),
        *sorted(others),
        *sorted(otherfiles),
    ]

    result_text = ""
    fls, fos = 0, 0
    flc, foc = 0, 0

    for i in omk:
        try:
            emoji = i.split()[0]
            name = i.split(maxsplit=1)[1]
            nam = name.split("/")[-1]
            if os.path.isdir(name):
                size = sum(
                    os.path.getsize(os.path.join(path, f))
                    for path, dirs, files in os.walk(name)
                    for f in files
                )
                if hb(size):
                    result_text += emoji + f" `{nam}`" + "  `" + hb(size) + "`\n"
                    fos += size
                else:
                    result_text += emoji + f" `{nam}`" + "\n"
                foc += 1
            else:
                if hb(int(os.path.getsize(name))):
                    result_text += (
                        emoji
                        + f" `{nam}`"
                        + "  `"
                        + hb(int(os.path.getsize(name)))
                        + "`\n"
                    )
                    fls += int(os.path.getsize(name))
                else:
                    result_text += emoji + f" `{nam}`" + "\n"
                flc += 1
        except Exception:
            pass

    tfos, tfls, ttol = hb(fos), hb(fls), hb(fos + fls)
    if not hb(fos):
        tfos = "0 B"
    if not hb(fls):
        tfls = "0 B"
    if not hb(fos + fls):
        ttol = "0 B"

    result_text += f"\n\n`Folders` :  `{foc}` :   `{tfos}`\n`Files` :       `{flc}` :   `{tfls}`\n`Total` :       `{flc+foc}` :   `{ttol}`"

    try:
        await client.send_message(
            message.chat.id, result_text, reply_to_message_id=message.id
        )
    except errors.BadRequest:
        with io.BytesIO(str.encode(result_text)) as out_file:
            out_file.name = "output.txt"
            await client.send_document(
                message.chat.id,
                out_file,
                reply_to_message_id=message.id,
                caption=f"`{message.text}`",
            )
        await message.delete()
