import io
import sys
import traceback

from pyrogram import filters
from pyrogram.enums import ParseMode

from bot import ALLOWED_USERS, bot
from bot.utils.functions import run_cmd


@bot.on_message(filters.command("exec") & filters.user(ALLOWED_USERS))
async def exec_handler(client, message):
    if len(message.command) == 1:
        return await message.reply("Give something to execute.")

    cmd = message.text.split(" ", 1)[1]
    status_message = await message.reply("Processing...")
    stdout, stderr = await run_cmd(cmd)

    output = f"**✦ COMMAND:**\n`{cmd}`\n\n"
    if stderr:
        output += f"**✦ STDERR:**\n`{stderr}`\n\n"
    if stdout:
        output += f"**✦ STDOUT:**\n`{stdout}`"
    elif not stderr:
        output += "**✦ STDOUT:**\n`Success`"

    if len(output) > 4096:
        with io.BytesIO(str.encode(output)) as file:
            file.name = "exec.txt"
            await client.send_document(
                message.chat.id,
                file,
                caption=f"`{cmd[:998]}`",
                reply_to_message_id=message.reply_to_message_id or message.id,
                parse_mode=ParseMode.MARKDOWN,
            )
        await status_message.delete()
    else:
        await client.send_message(
            message.chat.id,
            output,
            reply_to_message_id=message.reply_to_message_id or message.id,
            parse_mode=ParseMode.MARKDOWN,
        )
        await status_message.delete()


@bot.on_message(filters.command("eval") & filters.user(ALLOWED_USERS))
async def eval_handler(client, message):
    if len(message.command) == 1:
        return await message.reply("Give something to evaluate.")

    cmd = message.text.markdown.split(" ", 1)[1]
    status_message = await message.reply("Processing...")

    old_stderr = sys.stderr
    old_stdout = sys.stdout

    redirected_output = sys.stdout = io.StringIO()
    redirected_error = sys.stderr = io.StringIO()
    stdout, stderr, exc = None, None, None

    try:
        await aexec(cmd, message)
    except Exception:
        exc = traceback.format_exc()

    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr

    evaluation = exc if exc else (stderr if stderr else stdout)
    final_output = (
        f"**✦ Code :**\n`{cmd}`\n\n**✦ Result :**\n`{evaluation or 'Success'}`\n"
    )

    if len(final_output) > 4096:
        with io.BytesIO(str.encode(evaluation)) as file:
            file.name = "eval.txt"
            await client.send_document(
                message.chat.id,
                file,
                caption=f"`{cmd[:998]}`",
                reply_to_message_id=message.reply_to_message_id or message.id,
                parse_mode=ParseMode.MARKDOWN,
            )
        await status_message.delete()
    else:
        await client.send_message(
            message.chat.id,
            final_output,
            reply_to_message_id=message.reply_to_message_id or message.id,
            parse_mode=ParseMode.MARKDOWN,
        )
        await status_message.delete()


async def aexec(code, message):
    exec(
        (
            "async def __aexec(client, message):\n"
            + "    p = print\n"
            + "    m = message\n"
            + "    reply = m.reply_to_message\n"
            + "    chat = m.chat.id"
        )
        + "".join(f"\n    {l}" for l in code.split("\n"))
    )

    return await locals()["__aexec"](message._client, message)
