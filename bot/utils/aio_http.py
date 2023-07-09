import json
import re
import time
from urllib.parse import unquote

import aiofiles
from aiohttp import ClientResponse, ClientSession

from bot.utils.singleton import Singleton


class AioHttp(metaclass=Singleton):
    session = None
    def __init__(self, *args, **kwargs):
        self.session = ClientSession(*args, **kwargs)

    async def request(
        url: str,
        method: str = "GET",
        data: dict = {},
        headers: dict = None,
        re_json: bool = False,
        re_res: bool = False,
        *args,
        **kwargs,
    ):
        session = self.session if self.session else ClientSession(headers=headers)

        try:
            if method.lower() == "post":
                response = await session.post(url, data=data, *args, **kwargs)
            else:
                response = await session.request(method, url, *args, **kwargs)

            if re_res:
                r = response
            elif re_json:
                r = json.loads(await response.text())
            else:
                r = await response.read()
        finally:
            if not self.session:
                await session.close()

        return r


    async def download(
        url: str,
        filename: str = None,
        headers: dict = None,
        progress_callback=None,
        *args,
        **kwargs,
    ):
        session = self.session if self.session else ClientSession(headers=headers)

        try:
            async with session.get(url, *args, **kwargs) as response:
                filename, total_size = get_name_and_size_from_response(
                    response, filename=filename
                )

                downloaded_size = 0
                start_time = time.time()

                async with aiofiles.open(filename, "wb") as file:
                    async for chunk in response.content.iter_chunked(1024):
                        if chunk:
                            await file.write(chunk)
                            downloaded_size += len(chunk)

                        if progress_callback and total_size:
                            await progress_callback(downloaded_size, total_size)

        finally:
            if not self.session:
                await session.close()

        return filename, time.time() - start_time, response.ok

    async def fast_download(
        url: str,
        filename: str = None,
        headers: dict = None,
        max_threads: int = 4,
        *args,
        **kwargs,
    ):
        session = self.session if self.session else ClientSession()

        try:
            async with session.get(url, headers=headers, *args, **kwargs) as response:
                filename, total_size = get_name_and_size_from_response(
                    response, filename=filename
                )

                chunk_size = total_size // max_threads

                tasks = []
                async with aiofiles.open(filename, "wb") as file:
                    for i in range(max_threads):
                        start = i * chunk_size
                        end = start + chunk_size if i < max_threads - 1 else None
                        task = asyncio.create_task(
                            self._download_achunk(
                                session, url, headers, start, end, file, *args, **kwargs
                            )
                        )
                        tasks.append(task)

                    await asyncio.gather(*tasks)

        finally:
            if not self.session:
                await session.close()   

        return filename, response.ok

    @staticmethod
    async def _download_achunk(
        session: ClientSession,
        url: str,
        headers: dict,
        start: int,
        end: int,
        file,
        *args,
        **kwargs,
    ):
        headers = {} if not headers else headers
        headers["Range"] = f"bytes={start}-{end}" if end else f"bytes={start}-"
        async with session.get(
            url, headers=headers, allow_redirects=True, *args, **kwargs
        ) as response:
            async for chunk in response.content.iter_chunked(1024):
                if chunk:
                    await file.seek(start)
                    await file.write(chunk)
                    start += len(chunk)


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
