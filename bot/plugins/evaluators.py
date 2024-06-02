import html
import io
import sys
import traceback

from pyrogram import Client, filters
from pyrogram.enums import ParseMode

from bot import ALLOWED_USERS
from bot.utils.functions import run_cmd


@Client.on_message(filters.command("exec") & filters.user(ALLOWED_USERS))
async def exec_handler(client, message):
    if len(message.command) == 1:
        return await message.reply("Give something to execute.")

    cmd = message.text.split(" ", 1)[1]
    status_message = await message.reply("Processing...")
    stdout, stderr = await run_cmd(cmd)

    output = f"<b>→ COMMAND:</b>\n<pre language='bash'>{cmd}</pre>\n\n"
    if stderr:
        output += f"<b>→ STDERR:</b>\n<pre>{stderr}</pre>\n\n"
    if stdout:
        output += f"<b>→ STDOUT:</b>\n<pre>{stdout}</pre>"
    elif not stderr:
        output += "<b>→ STDOUT:</b>\n<pre>Success</pre>"

    if len(output) > 4096:
        with io.BytesIO(str.encode(output)) as file:
            file.name = "exec.txt"
            await client.send_document(
                message.chat.id,
                file,
                caption=f"<pre language='bash'>{cmd[:998]}</pre>",
                reply_to_message_id=message.reply_to_message_id or message.id,
                parse_mode=ParseMode.HTML,
            )
    else:
        await client.send_message(
            message.chat.id,
            output,
            reply_to_message_id=message.reply_to_message_id or message.id,
            parse_mode=ParseMode.HTML,
        )

    await status_message.delete()


@Client.on_message(filters.command("eval") & filters.user(ALLOWED_USERS))
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

    evaluation = exc or (stderr or stdout)
    final_output = f"<b>→ Code :</b>\n<pre language='python'>{cmd}</pre>\n\n<b>→ Result :</b>\n<pre>{html.escape(evaluation, quote=False) or 'Success'}</pre>\n"
    if len(final_output) > 4096:
        with io.BytesIO(str.encode(evaluation)) as file:
            file.name = "eval.txt"
            await client.send_document(
                message.chat.id,
                file,
                caption=f"<pre language='python'>{cmd[:998]}</pre>",
                reply_to_message_id=message.reply_to_message_id or message.id,
                parse_mode=ParseMode.HTML,
            )
    else:
        await client.send_message(
            message.chat.id,
            final_output,
            reply_to_message_id=message.reply_to_message_id or message.id,
            parse_mode=ParseMode.HTML,
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
