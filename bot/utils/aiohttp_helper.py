import asyncio
import json
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
                raise ValueError("Could not get size from url.")

            start = -1
            chunk_size = total_size // max_threads
            ranges = []
            start_time = time.time()
            async with aiofiles.open(filename, "wb") as file:
                for i in range(max_threads - 1):
                    ranges.append((start + 1, start + chunk_size))
                    start += chunk_size
                ranges.append((start + 1, total_size))
                async with asyncio.TaskGroup() as tg:
                    for start, end in ranges:
                        task = tg.create_task(
                            self.download_achunk(url, headers, start, end, file)
                        )

            return filename, time.time() - start_time, response.ok

    async def download_achunk(
        self, url: str, headers: dict, start: int, end: int, file, **kwargs
    ):
        headers = {} if not headers else headers
        headers["Range"] = f"bytes={start}-{end}" if end else f"bytes={start}-"
        async with self.get_session().get(
            url, headers=headers, allow_redirects=True, **kwargs
        ) as response:
            if not response.status == 206:
                raise ValueError("Url does not support multi-threaded download.")
            async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                if chunk:
                    await file.seek(start)
                    await file.write(chunk)
                    start += len(chunk)

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
