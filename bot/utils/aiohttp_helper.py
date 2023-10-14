import asyncio
import json
import re
import threading
import time
from urllib.parse import unquote

import aiofiles
from aiohttp import ClientResponse, ClientSession, TCPConnector

from bot.utils.singleton import Singleton


class AioHttpManager(metaclass=Singleton):
    def __init__(self, max_sessions, connector=TCPConnector(limit=25)):
        self.max_sessions = max_sessions
        self.sessions = [self._create_session(connector) for _ in range(max_sessions)]
        self.lock = threading.Lock()

    def _create_session(self, connector=None):
        
        return {"session": ClientSession(connector=connector) if connector else ClientSession(), "usage_count": 0}

    def get_session(self):
        with self.lock:
            lowest_usage_session = min(self.sessions, key=lambda s: s["usage_count"])
            lowest_usage_session["usage_count"] += 1
            return lowest_usage_session["session"]

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
        chunk_size: int = 1024,
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
        max_threads: int = 4,
        **kwargs,
    ):
        session = self.get_session()
        async with session.get(url, **kwargs) as response:
            filename, total_size = self.get_name_and_size_from_response(
                response, filename=filename
            )

            chunk_size = total_size // max_threads
            start_time = time.time()
            tasks = []
            async with aiofiles.open(filename, "wb") as file:
                for i in range(max_threads):
                    start = i * chunk_size
                    end = start + chunk_size if i < max_threads - 1 else None
                    task = asyncio.create_task(
                        self.download_achunk(session, url, headers, start, end, file)
                    )
                    tasks.append(task)

                await asyncio.gather(*tasks)

            return filename, time.time() - start_time, response.ok

    async def download_achunk(
        self,
        session: ClientSession,
        url: str,
        headers: dict,
        start: int,
        end: int,
        file,
        **kwargs,
    ):
        headers = {} if not headers else headers
        headers["Range"] = f"bytes={start}-{end}" if end else f"bytes={start}-"
        async with session.get(
            url, headers=headers, allow_redirects=True, **kwargs
        ) as response:
            async for chunk in response.content.iter_chunked(1024):
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
