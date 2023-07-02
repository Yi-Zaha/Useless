import math
import time

from bot.utils.functions import humanbytes, readable_time

No_Flood = {}


async def progress_cb(
    current, total, message, start, ps_type, file_name=None, delay_edit=None
):
    now = time.time()

    if delay_edit:
        if No_Flood.get(message.chat.id, {}).get(message.id, 0) > now - 1.1:
            return
        No_Flood.setdefault(message.chat.id, {})[message.id] = now

    diff = time.time() - start
    if round(diff % 10.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        time_to_completion = round((total - current) / speed) * 1000
        progress_str = "`[{0}{1}] {2}%`\n\n".format(
            "●" * math.floor(percentage / 5),
            "" * (20 - math.floor(percentage / 5)),
            round(percentage, 2),
        )

        tmp = (
            progress_str
            + "`{0} of {1}`\n\n`✦ Speed: {2}/s`\n\n`✦ ETA: {3}`\n\n".format(
                humanbytes(current),
                humanbytes(total),
                humanbytes(speed),
                readable_time(time_to_completion / 1000),
            )
        )
        if file_name:
            try:
                await message.edit(
                    "**✦ Status :** `{}`\n\n`File Name: {}`\n\n{}".format(
                        ps_type, file_name, tmp
                    )
                )
            except BaseException:
                pass
        else:
            try:
                await message.edit("**✦ Status :** `{}`\n\n{}".format(ps_type, tmp))
            except BaseException:
                pass
