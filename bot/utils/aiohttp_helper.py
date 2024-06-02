import asyncio
import json
import os
import re
import time
from urllib.parse import unquote

import aiofiles
from aiohttp import ClientResponse, ClientSession
from pyrogram import StopTransmission

from bot.logger import LOGGER

CHUNK_SIZE = 1024
MAX_THREADS = 4


class AioHttpHelper:
    def __init__(self, max_sessions, *args, **kwargs):
        self.max_sessions = max_sessions
        self.args = args
        self.kwargs = kwargs
        self.sessions = [self._create_session() for _ in range(max_sessions)]
        self.lock = asyncio.Lock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _create_session(self):
        return {
            "session": ClientSession(*self.args, **self.kwargs),
            "usage_count": 0,
        }

    async def get_session(self):
        async with self.lock:
            if not self.sessions:
                self.sessions = [
                    self._create_session() for _ in range(self.max_sessions)
                ]
            lowest_usage_session = min(self.sessions, key=lambda s: s["usage_count"])
            lowest_usage_session["usage_count"] += 1
            session = lowest_usage_session["session"]
            if session.closed:
                self.sessions.remove(lowest_usage_session)
                self.sessions.append(self._create_session())
                return self.sessions[-1]["session"]
            return session

    async def close(self):
        for n, s in enumerate(self.sessions):
            self.sessions.remove(s)
            try:
                await s["session"].close()
            except Exception as e:
                LOGGER(__name__).error(f"Could not close session ({n}): {e}")

    async def request(
        self,
        url: str,
        method: str = "GET",
        re_json: bool = False,
        re_res: bool = False,
        **kwargs,
    ):
        session = await self.get_session()
        async with session.request(method, url, **kwargs) as response:
            if re_res:
                return response
            return (
                json.loads(await response.text()) if re_json else await response.read()
            )

    async def download(
        self,
        url: str,
        filename: str = None,
        progress_callback=None,
        chunk_size: int = CHUNK_SIZE,
        **kwargs,
    ):
        session = await self.get_session()
        async with session.get(url, **kwargs) as response:
            filename, total_size = self.get_name_and_size_from_response(
                response, filename=filename
            )
            downloaded_size = 0
            start_time = time.time()

            async with aiofiles.open(filename, "wb") as file:
                async for chunk in response.content.iter_chunked(chunk_size):
                    if chunk:
                        await file.write(chunk)
                        downloaded_size += len(chunk)
                    if progress_callback and total_size:
                        try:
                            await progress_callback(downloaded_size, total_size)
                        except StopTransmission:
                            if os.path.exists(filename):
                                os.remove(filename)
                            return None, time.time() - start_time, response.ok

            return filename, time.time() - start_time, response.ok

    async def fast_download(
        self,
        url: str,
        filename: str = None,
        headers: dict = None,
        max_threads: int = MAX_THREADS,
        **kwargs,
    ):
        session = await self.get_session()
        async with session.get(url, **kwargs) as response:
            filename, total_size = self.get_name_and_size_from_response(
                response, filename=filename
            )

            if not total_size:
                raise ValueError("Could not get size from the URL.")

            start_time = time.time()
            tasks = []

            async def download_part(start, end, part_n):
                range_headers = headers or {}
                range_headers["Range"] = f"bytes={start}-{end}"
                async with session.get(
                    url, headers=range_headers, **kwargs
                ) as part_response:
                    if part_response.status != 206:
                        raise ValueError(
                            "URL does not support multi-threaded download."
                            if part_n < 1
                            else f"URL does not support {max_threads} multi-threaded download."
                        )
                    async with aiofiles.open(
                        f"{filename}.part-{part_n}", "wb"
                    ) as file_part:
                        async for chunk in part_response.content.iter_any():
                            if chunk:
                                await file_part.write(chunk)

            part_size = total_size // max_threads
            for part_n in range(max_threads):
                start = part_n * part_size
                end = (
                    (part_n + 1) * part_size - 1
                    if part_n < max_threads - 1
                    else total_size
                )
                tasks.append(asyncio.create_task(download_part(start, end, part_n)))
            try:
                await asyncio.gather(*tasks)
            except BaseException:
                for part_n in range(max_threads):
                    if os.path.exists(f"{filename}.part-{part_n}"):
                        os.remove(f"{filename}.part-{part_n}")
                raise

            async with aiofiles.open(filename, "wb") as final_file:
                for part_n in range(max_threads):
                    async with aiofiles.open(
                        f"{filename}.part-{part_n}", "rb"
                    ) as file_part:
                        try:
                            while True:
                                chunk = await file_part.read(CHUNK_SIZE)
                                if not chunk:
                                    break
                                await final_file.write(chunk)
                        finally:
                            os.remove(f"{filename}.part-{part_n}")

            return filename, time.time() - start_time, response.ok

    async def download_achunk(
        self, url: str, start: int, end: int, filename: str, headers: dict, **kwargs
    ):
        headers = headers or {}
        headers["Range"] = f"bytes={start}-{end}"
        session = await self.get_session()
        async with session.get(url, headers=headers, **kwargs) as response:
            if response.status != 206:
                raise ValueError("URL does not support multi-threaded download.")
            async with aiofiles.open(filename, "wb") as file:
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    if chunk:
                        await file.write(chunk)
                return filename

    @staticmethod
    def get_name_and_size_from_response(response: ClientResponse, filename: str = None):
        if filename is None:
            if content_disp := response.headers.get("Content-Disposition"):
                filename = re.search(r"filename=(.*?)(;|$)", content_disp)
                if filename:
                    filename = unquote(filename[1].replace('"', "") or "")

        if not filename:
            filename = unquote(response.url.raw_name)

        total_size = int(response.headers.get("content-length", 0)) or int(
            response.headers.get("Content-Range", "bytes 0-0/0").split("/")[-1]
        )

        return filename, total_size


AioHttp = AioHttpHelper(2)
