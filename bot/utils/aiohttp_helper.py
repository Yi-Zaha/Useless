import json
import re
import time
from urllib.parse import unquote

import aiofiles
from aiohttp import ClientResponse, ClientSession


class AioHttp:
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
        async with ClientSession(headers=headers) as session:
            if method.lower() == "post":
                response = await session.post(url, data=data, *args, **kwargs)
            elif method.lower() == "head":
                response = await session.head(url, *args, **kwargs)
            else:
                response = await session.get(url, *args, **kwargs)
            if re_res:
                return response
            elif re_json:
                return json.loads(await response.text())
            else:
                return await response.read()

    async def download(
        url: str,
        filename: str = None,
        headers: dict = None,
        progress_callback=None,
        *args,
        **kwargs,
    ):
        async with ClientSession(headers=headers) as session:
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

                    return filename, time.time() - start_time, response.ok

    async def fast_download(
        url: str,
        filename: str = None,
        headers: dict = None,
        max_threads: int = 4,
        *args,
        **kwargs,
    ):
        async with ClientSession() as session:
            async with session.get(url, headers=headers, *args, **kwargs) as response:
                filename, total_size = get_name_and_size_from_response(
                    response, filename=filename
                )

                chunk_size = total_size // max_threads

                tasks = []
                async with aiofiles.open(filename, "wb") as file:
                    for i in range(max_threads):
                        start = i * chunk_size
                        end = start + chunk_size if i < num_threads - 1 else None
                        task = asyncio.create_task(
                            AioHttp.download_achunk(
                                session, url, headers, start, end, file
                            )
                        )
                        tasks.append(task)

                    await asyncio.gather(*tasks)

                    return filename, response.ok

    async def download_achunk(
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
