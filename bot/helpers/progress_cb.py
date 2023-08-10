import io
import math
import time
from typing import BinaryIO

from bot.utils.functions import humanbytes, readable_time

NO_FLOOD = {}


class Stream(io.BytesIO):
    def __init__(
        self, name: str, file_size: int, stream: BinaryIO, chunk_size: int = 512 * 1024
    ):
        super().__init__()
        self.buffer = b""
        self.stream = stream.__aiter__()
        self.chunk_size = chunk_size
        self.name = name
        self.file_size = file_size

    def read(self, n):
        try:
            return self.buffer[:n]
        finally:
            self.buffer = self.buffer[n:]

    async def progress(self, current, total, *args):
        if len(self.buffer) < self.chunk_size and current + self.chunk_size <= total:
            await self.fill()
        if args:
            await progress_cb(current, total, *args)

    async def fill(self):
        self.buffer += await self.stream.__anext__()

    def tell(self) -> int:
        return self.file_size

    def seek(self, n, seek_type=None):
        pass

    def getvalue(self):
        return self.buffer


async def progress_cb(
    current, total, message, start, ps_type, file_name=None, delay_edit=None
):
    now = time.time()

    if delay_edit:
        if NO_FLOOD.get(message.chat.id, {}).get(message.id, 0) > now - 1.1:
            return
        NO_FLOOD.setdefault(message.chat.id, {})[message.id] = now

    diff = now - start
    if round(diff % 10.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        time_to_completion = round((total - current) / speed) * 1000

        progress_width = 20
        completed_width = math.floor((percentage / 100) * progress_width)
        remaining_width = progress_width - completed_width

        progress_bar = "█" * completed_width + "░" * remaining_width

        stats = (
            f"**Current:** {humanbytes(current)} | **Total:** {humanbytes(total)}\n"
            f"**Speed:** {humanbytes(speed)}/s | **ETA:** {readable_time(time_to_completion / 1000)}\n"
        )

        if file_name:
            try:
                await message.edit(
                    f"**Status:** `{ps_type}`\n\n"
                    f"**File Name:** `{file_name}`\n\n"
                    f"**Progress:** `{progress_bar}`\n\n"
                    f"{stats}"
                )
            except BaseException:
                pass
        else:
            try:
                await message.edit(
                    f"**Status:** `{ps_type}`\n\n"
                    f"**Progress:** `{progress_bar}`\n\n"
                    f"{stats}"
                )
            except BaseException:
                pass
