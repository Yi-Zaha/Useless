import asyncio
import json
import os
import re
import threading
import time
from urllib.parse import unquote

import aiofiles
from aiohttp import ClientResponse, ClientSession, TCPConnector

CHUNK_SIZE = 1024
MAX_THREADS = 4


class AioHttpManager:
    def __init__(self, max_sessions, connector=TCPConnector(limit=50)):
        self.max_sessions = max_sessions
        self.connector = connector
        self.sessions = [self._create_session() for _ in range(max_sessions)]
        self.lock = threading.Lock()

    def _create_session(self, connector=None):
        return {
            "session": ClientSession(connector=self.connector)
            if self.connector
            else ClientSession(),
            "usage_count": 0,
        }

    def get_session(self):
        with self.lock:
            lowest_usage_session = min(self.sessions, key=lambda s: s["usage_count"])
            lowest_usage_session["usage_count"] += 1
            session = lowest_usage_session["session"]
            if session.closed:
                self.sessions.remove(lowest_usage_session)
                self.sessions.append(self._create_session())
                return self.sessions[-1]["session"]
            return session

    async def close(self):
        for s in self.sessions:
            await s["session"].close()

    async def request(
        self,
        url: str,
        method: str = "GET",
        re_json: bool = False,
        re_res: bool = False,
        **kwargs,
    ):
        async with self.get_session().request(method, url, **kwargs) as response:
            if re_res:
                return response
            if re_json:
                return json.loads(await response.text())
            return await response.read()

    async def download(
        self,
        url: str,
        filename: str = None,
        progress_callback=None,
        chunk_size: int = CHUNK_SIZE,
        **kwargs,
    ):
        async with self.get_session().get(url, **kwargs) as response:
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
                        await progress_callback(downloaded_size, total_size)

            return filename, time.time() - start_time, response.ok

    async def fast_download(
        self,
        url: str,
        filename: str = None,
        headers: dict = None,
        max_threads: int = MAX_THREADS,
        **kwargs,
    ):
        session = self.get_session()
        async with session.get(url, **kwargs) as response:
            filename, total_size = self.get_name_and_size_from_response(
                response, filename=filename
            )

            if not total_size:
                raise ValueError("Could not get size from the URL.")

            start_time = time.time()
            tasks = []

            async def download_part(start, end, part_n):
                range_headers = {} if not headers else headers
                range_headers["Range"] = f"bytes={start}-{end}"
                async with self.get_session().get(
                    url, headers=range_headers, **kwargs
                ) as part_response:
                    if part_response.status != 206:
                        raise ValueError(
                            "URL does not support multi-threaded download."
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

            await asyncio.gather(*tasks)

            # Merge downloaded parts into the final file
            async with aiofiles.open(filename, "wb") as final_file:
                for part_n in range(max_threads):
                    async with aiofiles.open(
                        f"{filename}.part-{part_n}", "rb"
                    ) as file_part:
                        while True:
                            chunk = await file_part.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            await final_file.write(chunk)
                    # Remove the downloaded part file after merging
                    os.remove(f"{filename}.part-{part_n}")

            return filename, time.time() - start_time, response.ok

    async def download_achunk(
        self, url: str, start: int, end: int, filename: str, headers: dict, **kwargs
    ):
        headers = {} if not headers else headers
        headers["Range"] = f"bytes={start}-{end}"
        async with self.get_session().get(url, headers=headers, **kwargs) as response:
            if response.status != 206:
                raise ValueError("Url does not support multi-threaded download.")
            async with aiofiles.open(filename, "wb") as file:
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    if chunk:
                        await file.write(chunk)
                return filename

    @staticmethod
    def get_name_and_size_from_response(response: ClientResponse, filename: str = None):
        if filename is None:
            content_disp = response.headers.get("Content-Disposition")
            if content_disp:
                filename = re.findall(r'filename="(.*?)"', content_disp)
                if filename:
                    filename = unquote(filename[0].strip() or "")

        if not filename:
            filename = unquote(response.url.raw_name)

        total_size = int(response.headers.get("content-length", 0)) or int(
            response.headers.get("Content-Range", "bytes 0-0/0").split("/")[-1]
        )

        return filename, total_size


AioHttp = AioHttpManager(4)
