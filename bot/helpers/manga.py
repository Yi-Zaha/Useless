import ast
import asyncio
import base64
import html
import json
import os
import random
import re
import shutil
import tempfile
from urllib.parse import urljoin, urlparse

import pyminizip
from bs4 import BeautifulSoup

from bot import bot
from bot.utils import user_agents
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.functions import (
    async_wrap,
    file_to_graph,
    get_link,
    get_soup,
    images_to_graph,
    retry_func,
)
from bot.utils.pdf import encrypt_pdf, get_path, images_to_pdf, imgtopdf, resize_img

proxy_url = "https://hdome.onrender.com/proxy"


class _BASE:
    @staticmethod
    async def download_images(
        image_urls, directory=None, headers=None, sequentially=False
    ):
        directory = directory or tempfile.mkdtemp()
        directory = directory.rstrip("/")
        images = []
        tasks = []

        for n, url in enumerate(image_urls):
            if url in (None, ""):
                continue
            ext = os.path.splitext(url)
            ext = ext[1] if len(ext) > 1 else ".jpg"
            image = f"{directory}/{n}{ext}"
            images.append(image)
            task = retry_func(AioHttp.download, url, filename=image, headers=headers)
            tasks.append(task)

        try:
            if sequentially:
                for task in tasks:
                    await task
            else:
                await asyncio.gather(*tasks)
        except Exception:
            shutil.rmtree(directory)
            raise

        return images, directory

    @staticmethod
    async def fetch_images(url, content=None, _class="wp-manga-chapter-img", src="src"):
        if not content:
            response = await get_link(url, cloud=True)
            content = response.content

        soup = BeautifulSoup(content, "html.parser")
        image_urls = []

        if "manganato" in url or "manganelo" in url:
            image_urls = [
                img.get("src") or img.get("data-src")
                for img in soup.find("div", "container-chapter-reader").find_all("img")
            ]
        elif "mangabuddy" in url:
            regex = r"var chapImages = '(.*)'"
            image_urls = re.findall(regex, soup.prettify())[0].split(",")
        elif "hentai2read" in url:
            img_base = "https://static.hentai.direct/hentai"
            regex = r"'images' : (.*)"
            image_urls = ast.literal_eval(
                re.findall(regex, soup.prettify())[0].strip(",")
            )
            image_urls = [img_base + img.replace("\\", "") for img in image_urls]
        elif "mangatoto" in url:
            regex = r"const imgHttpLis = (.*);"
            image_urls = ast.literal_eval(re.findall(regex, soup.prettify())[0])
        elif "mangapark" in url:
            data = json.loads(soup.find("script", id="__NEXT_DATA__").text)
            image_set = data["props"]["pageProps"]["dehydratedState"]["queries"][0][
                "state"
            ]["data"]["data"]["imageSet"]
            image_urls = [
                f"{link}?{extra}"
                for link, extra in zip(image_set["httpLis"], image_set["wordLis"])
            ]
        elif "mangadistrict" in url:
            div = soup.find("div", "reading-content")
            images = div.find_all("img", "wp-manga-chapter-img") if div else None
            image_urls = [
                (
                    img.get("data-wpfc-original-src").strip()
                    if img.get("data-wpfc-original-src", "").strip().startswith("http")
                    else img.get("src").strip()
                )
                for img in images
            ]
        elif "api.comick." in url:
            if "tachiyomi" not in url:
                data = json.loads(content)
                chapter = None

                for item in data["chapters"]:
                    if not item["group_name"]:
                        break
                    for group in item["group_name"]:
                        if "official" in group.lower():
                            chapter = item
                            break
                if chapter is None:
                    chapter = data["chapters"][-1]

                content = (
                    await get_link(
                        f'https://api.comick.fun/chapter/{chapter["hid"]}?tachiyomi=true',
                        cloud=True,
                    )
                ).text

            data = json.loads(content)
            image_urls = [
                image["url"] for image in data["chapter"]["images"] if image.get("url")
            ]
        elif "manga18.club" in url:
            images_script = next(
                script.text
                for script in soup.find_all("script")
                if "slides_p_path" in script.text
            )
            images_data = json.loads(
                re.search(r"var slides_p_path = (.*),]", images_script).group(1) + "]"
            )
            image_urls = [
                base64.b64decode(img_data).decode() for img_data in images_data
            ]
        else:
            images = soup.find_all("img", _class)
            image_urls = [
                (img.get(src) or img.get("data-src") or "").strip() for img in images
            ]

        return image_urls

    @staticmethod
    async def dl_chapter(
        chapter_url,
        title,
        mode,
        file_pass=None,
        author=None,
        author_url=None,
        _class="wp-manga-chapter-img",
        src="src",
        image_downloader=_BASE.download_images,
    ):
        headers = {"User-Agent": random.choice(user_agents)}
        response = await get_link(chapter_url, headers=headers, cloud=True)
        image_urls = await _BASE.fetch_images(
            chapter_url, content=response.text, _class=_class, src=src
        )
        if not image_urls:
            raise ValueError("Couldn't fetch image urls.")
        headers["Referer"] = str(response.url)

        files = []
        images = []
        mode = mode.lower()

        if "graph" in mode or mode == "all":
            first_res = await AioHttp.request(image_urls[0], re_res=True)
            if first_res.ok:
                graph_url = await images_to_graph(title, image_urls)
            else:
                if not images:
                    images, temp_dir = await image_downloader(
                        image_urls, headers=headers
                    )
                proxy_image_urls = []
                try:
                    for image in images:
                        await async_wrap(resize_img)(image)
                        proxy_image_urls.append(await file_to_graph(image))
                except Exception as e:
                    print(e)
                    proxy_image_urls = [
                        f"{proxy_url}?src={url}&referer={chapter_url}"
                        for url in image_urls
                    ]
                graph_url = await images_to_graph(
                    title,
                    proxy_image_urls,
                    author=author,
                    author_url=author_url,
                )
            files.append(graph_url)

        if "pdf" in mode or mode in ("both", "all"):
            if not images:
                images, temp_dir = await image_downloader(image_urls, headers=headers)
            pdf_file = get_path(f"{title}.pdf")
            pdf_author = author or ""
            if author_url:
                pdf_author += f" | {author_url}" if author else author_url
            try:
                await imgtopdf(pdf_file, images, author=pdf_author)
            except Exception:
                await images_to_pdf(pdf_file, images, author=pdf_author)

            if file_pass:
                pdf_file = encrypt_pdf(pdf_file, file_pass)
            files.append(pdf_file)

        if "cbz" in mode or mode in ("both", "all"):
            if not images:
                images, temp_dir = await image_downloader(image_urls, headers=headers)
            cbz_file = get_path(f"{title}.cbz")
            pyminizip.compress_multiple(images, [], str(cbz_file), file_pass, 9)
            files.append(cbz_file)

        if images:
            shutil.rmtree(temp_dir)
        return files[0] if len(files) == 1 else files


class IManga(_BASE):
    def __init__(self, manga_id, nelo=False):
        self.base_url = (
            "https://ww5.manganelo.tv/manga/" if nelo else "https://chapmanganato.com/"
        )
        self.nelo = nelo
        self.url = ""
        self.id = manga_id
        self.title = ""
        self.alternatives = ""
        self.status = ""
        self.poster_url = ""
        self.description = ""
        self.genres = []
        self.views = ""
        self.authors = []
        self.updated = ""
        self.chapters = {}

    async def _parse_info(self):
        headers = {"User-Agent": random.choice(user_agents)}
        url = urljoin(self.base_url, self.id)
        response = await get_link(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        self.url = str(response.url)
        self.title = soup.select_one(".story-info-right h1").text.strip()
        self.alternatives = soup.select_one(".story-info-right h2") or "N/A"
        self.status = (
            soup.find("i", class_="info-status")
            .find_next("td", class_="table-value")
            .text.strip()
        )
        self.poster_url = soup.select_one(".story-info-left img.img-loading")["src"]
        if self.nelo and self.poster_url:
            self.poster_url = f"https://ww5.manganelo.tv{self.poster_url}"
        self.description = html.unescape(
            soup.select_one(".panel-story-info-description").text.strip()
        )
        self.genres = [
            x.text.strip()
            for x in soup.find("i", class_="info-genres")
            .findNext("td", class_="table-value")
            .find_all("a", "a-h")
        ]
        self.views = soup.find("div", class_="story-info-right-extent").find_all(
            "span", class_="stre-value"
        )
        self.views = self.views[1].text.strip() if len(self.views) > 1 else None
        self.authors = [
            x.strip()
            for x in soup.find("i", class_="info-author")
            .find_next("td", class_="table-value")
            .text.split(" - ")
        ]
        self.updated = soup.select_one(
            ".story-info-right-extent span.stre-value"
        ).text.strip()
        self.chapters = self._parse_chapters(soup)
        return self

    def _parse_chapters(self, soup):
        data = {}
        panels = [
            x.find("a")
            for x in soup.find(class_="panel-story-chapter-list").find_all(class_="a-h")
        ]

        for c in reversed(panels):
            chapter = c["href"].split("-")[-1].strip()
            link = c["href"]
            if not link.startswith("http"):
                link = f"https://ww5.manganelo.tv{link}"
            data[chapter] = link
        return data

    @staticmethod
    async def dl_chapter(chapter_url, title, mode, file_pass=None):
        return await _BASE.dl_chapter(
            chapter_url=chapter_url,
            title=title,
            mode=mode,
            file_pass=file_pass,
            author=bot.me.first_name,
            author_url=f"https://telegram.me/{bot.me.username}",
        )


class PS(_BASE):
    __all__ = [
        "Toonily",
        "Manhwa18",
        "MangaDistrict",
        "Manga18Club",
        "Manganato",
        "Mangabuddy",
        "Comick",
    ]

    @staticmethod
    def guess_ps(link):
        if "toonily.com" in link:
            return "Toonily"
        elif "manhwa18.cc" in link:
            return "Manhwa18"
        elif "manganato" in link:
            return "Manganato"
        elif "mangabuddy.com" in link:
            return "Mangabuddy"
        elif "mangadistrict.com" in link:
            return "MangaDistrict"
        elif "comick.fun" in link or "comick.app" in link:
            return "Comick"
        elif "manga18.club" in link:
            return "Manga18Club"
        raise ValueError("Invalid PS Link")

    @staticmethod
    def iargs(inp):
        data = {"-t": "Toonily", "-18": "Manhwa18", "-md": "MangaDistrict"}
        for tag, name in data.items():
            if inp == tag:
                return name
            if inp == name:
                return tag

    @staticmethod
    async def get_title(link, ps=None):
        ps = ps or PS.guess_ps(link)

        if ps == "Manhwa18":
            bs = await get_soup(link, cloud=True)
            title = (
                bs.title.string.replace("Read", "")
                .strip()
                .split("Manhwa at")[0]
                .strip()
            )

        elif ps == "Toonily":
            bs = await get_soup(link, cloud=True)
            title = (
                bs.title.string.replace("Read", "")
                .replace("Manga - Toonily", "")
                .strip()
            )

        elif ps == "Manganato":
            bs = await get_soup(link, cloud=True)
            title = bs.find(class_="story-info-right").find("h1").text.strip()

        elif ps == "Mangabuddy":
            bs = await get_soup(link, cloud=True)
            title = bs.find("div", "name box").find("h1").text

        elif ps == "MangaDistrict":
            bs = await get_soup(link, cloud=True)
            title = bs.find("div", "post-title").find("h1").text.strip()

        elif ps == "Comick":
            base = "https://api.comick.fun"
            if base[:-4] not in link:
                hid = link.split("/")[-1].split("?")[0]
                link = f"{base}/comic/{hid}"
            data = (await get_link(link, cloud=True)).json()
            title = data["comic"]["title"]

        elif ps == "Manga18Club":
            bs = await get_soup(link, cloud=True)
            title = bs.find("div", "detail_name").find("h1").text.strip()

        else:
            raise ValueError(f"Invalid Site: {ps!r}")

        return title.replace("’", "'").replace("'S", "'s")

    @staticmethod
    async def iter_chapters(link, ps=None, comick_vol=None):
        link = link
        ps = ps or PS.guess_ps(link)

        if ps == "Manhwa18":
            bs = await get_soup(link, cloud=True)
            for item in bs.find_all("a", "chapter-name text-nowrap"):
                yield None, urljoin("https://manhwa18.cc/", item["href"])

        elif ps == "Toonily":
            bs = await get_soup(link, cloud=True)
            for item in bs.find_all("li", "wp-manga-chapter"):
                yield None, item.find("a")["href"]

        elif ps == "Manganato":
            manga_base, manga_id = link.rstrip("/").rsplit("/", 1)
            manga = IManga(manga_id)
            manga.base_url = manga_base
            manga = await manga._parse_info()
            for ch, ch_url in reversed(manga.chapters.items()):
                yield ch, ch_url

        elif ps == "Mangabuddy":
            base = "https://mangabuddy.com/"
            splited = link.split("/")
            manga_id = splited[-1] or splited[-2]
            link = f"{base}api/manga/{manga_id}/chapters?source=detail"
            bs = await get_soup(link, cloud=True)
            for item in bs.find("ul", id="chapter-list").findAll("li"):
                yield None, urljoin(base, item.find("a")["href"])

        elif ps == "MangaDistrict":
            match = re.search(
                r"var manga = (.*);", (await get_link(link, cloud=True)).text
            )
            manga = ast.literal_eval(match[1]) if match else {}
            bs = await get_soup(
                link.rstrip("/") + "/ajax/chapters",
                cloud=True,
                post=True,
                data={"action": "get_chapters", "manga_id": manga.get("id")},
            )
            if uls := bs.find_all("ul", "sub-chap-list"):
                items = uls[-1].find_all("li", "wp-manga-chapter")

            else:
                items = bs.find_all("li", "wp-manga-chapter")
            for item in items:
                if item.find("a"):
                    yield None, item.find("a")["href"]

        elif ps == "Comick":
            base = "https://api.comick.fun"
            if base[:-4] not in link:
                hid = link.split("/")[-1].split("?")[0]
                link = f"{base}/comic/{hid}/chapters?lang=en"
            data = (await get_link(f"{link}&limit=10000", cloud=True)).json()
            yielded = []
            for chapter in data["chapters"]:
                if comick_vol:
                    if chapter["chap"] or not chapter["vol"]:
                        continue
                elif not chapter["chap"]:
                    continue

                if chapter["chap"]:
                    text = chapter["chap"]
                elif chapter["vol"]:
                    text = f'Vol - {chapter["vol"]}'
                else:
                    text = chapter["title"]
                if text in yielded:
                    continue
                yielded.append(text)

                if chapter["chap"]:
                    yield text, f'{link}&chap={chapter["chap"]}'
                else:
                    yield text, f'{base}/chapter/{chapter["hid"]}?tachiyomi=true'

        elif ps == "Manga18Club":
            base = "https://manga18.club/"
            bs = await get_soup(link, cloud=True)
            container = bs.find("div", "chapter_box")
            for item in container.find_all("div", "item"):
                yield None, urljoin(base, item.find("a")["href"])

        else:
            raise ValueError(f"Invalid Site: {ps!r}")

    @staticmethod
    async def updates(ps=None):
        ps = ps or PS.guess_ps(link)
        headers = {"User-Agent": random.choice(user_agents)}

        if ps == "Manhwa18":
            base = "https://manhwa18.cc/"
            content = await AioHttp.request(base, headers=headers)
            soup = BeautifulSoup(content, "html.parser")
            items = soup.find("div", "manga-lists")
            data = {}
            for item in items.find_all("div", "data wleft"):
                manga_url = urljoin(base, item.find("a")["href"])
                chapter_url = urljoin(
                    base, item.findNext("div", "chapter-item wleft").find("a")["href"]
                )
                data[manga_url] = chapter_url

        elif ps == "Toonily":
            base = "https://toonily.com/"
            content = await AioHttp.request(
                base, headers=headers, cookies={"toonily-mature": "1"}
            )
            soup = BeautifulSoup(content, "html.parser")
            items = soup.find_all("div", "page-item-detail manga")
            data = {}
            for item in items:
                manga_url = item.find("a")["href"]
                chapter_url = item.find("div", "chapter-item").find("a")["href"]
                data[manga_url] = chapter_url

        elif ps == "Manganato":
            base = "https://manganato.com/"
            content = await AioHttp.request(base, headers=headers)
            soup = BeautifulSoup(content, "html.parser")
            items = soup.find_all("div", "content-homepage-item")
            data = {}
            for item in items:
                manga_url = item.findNext("a")["href"]
                chapter_item = item.findNext("p", "a-h item-chapter")
                if not chapter_item:
                    continue
                chapter_url = chapter_item.findNext("a")["href"]
                data[manga_url] = chapter_url

        elif ps == "Mangabuddy":
            base = "https://mangabuddy.com/"
            home = "https://mangabuddy.com/home-page"
            content = await AioHttp.request(home, headers=headers)
            soup = BeautifulSoup(content, "html.parser")
            items = soup.find_all("div", "book-item latest-item")
            data = {}
            for item in items:
                manga_url = urljoin(base, item.a["href"])
                chapter_item = item.findNext("div", "chap-item")
                if not (chapter_item or chapter_item.a):
                    continue
                chapter_url = urljoin(base, chapter_item.a["href"])
                if manga_url not in data:
                    data[manga_url] = chapter_url

        elif ps == "MangaDistrict":
            base = "https://mangadistrict.com/"
            bs = await get_soup(base, cloud=True)
            items = bs.find_all("div", "page-item-detail")
            data = {}
            for item in items:
                manga_url = item.find("a").get("href")
                if manga_url not in data:
                    data[manga_url] = item.find("div", "chapter-item").find("a")["href"]

        elif ps == "Comick":
            base = "https://api.comick.fun"
            home = "https://comick.fun"
            updates_url = f"{base}/chapter?page=1&order=new&tachiyomi=true&accept_erotic_content=true"
            items = (await get_link(updates_url, cloud=True)).json()
            data = {}
            for item in items:
                manga_url = f'{home}/comic/{item["md_comics"]["hid"]}?lang=en'
                if manga_url not in data:
                    chapter_url = None
                    async for chapter in PS.iter_chapters(manga_url):
                        chapter_url = chapter[1]
                        break
                    if chapter_url:
                        data[manga_url] = chapter_url

        elif ps == "Manga18Club":
            base = "https://manga18.club/"
            latest = base + "list-manga"
            bs = await get_soup(latest, cloud=True)
            items = bs.find_all("div", {"class": "story_item"})
            data = {}
            for item in items:
                manga_url = item.find("a")["href"]
                if manga_url not in data:
                    data[manga_url] = urljoin(
                        base, item.find("div", "chapter_count").find("a")["href"]
                    )

        else:
            raise ValueError(f"Invalid Site: {ps!r}")
        return data

    @staticmethod
    async def download_images(*args, **kwargs):
        images, directory = await _BASE.download_images(*args, **kwargs)
        images.append("./bot/resources/phub_files_thumb.png")
        return images, directory

    @staticmethod
    async def dl_chapter(
        chapter_url,
        title,
        mode,
        file_pass=None,
        _class="wp-manga-chapter-img",
        src="src",
        image_downloader=PS.download_images,
    ):
        return await _BASE.dl_chapter(
            chapter_url=chapter_url,
            title=title,
            mode=mode,
            file_pass=file_pass,
            author="Pornhwa Hub",
            author_url="https://telegram.me/pornhwa_collection",
            _class=_class,
            src=src,
            image_downloader=image_downloader,
        )


class Nhentai:
    def __init__(self, code):
        self.base_url = "https://nhentai.net"
        self.cin_url = "https://cin.cam"
        if isinstance(code, int) or code.isdigit():
            self.code = str(code)

        else:
            self.code = code.rstrip("/").split("/")[-1]
        self.url = f"{self.base_url}/g/{self.code}"
        self.english_title = ""
        self.japanese_title = ""
        self.pretty_title = ""
        self.cover_url = ""
        self.pages = 0
        self.tags = []
        self.artists = []
        self.parodies = []
        self.characters = []
        self.languages = []
        self.categories = []
        self.image_urls = []

    @staticmethod
    async def doujins_from_url(url):
        parsed_url = urlparse(url)
        origin_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        content = await AioHttp.request(url)
        soup = BeautifulSoup(content, "html.parser")
        items = soup.find_all("a", "cover")
        doujins = []
        for item in items:
            doujin_code = item["href"].rstrip("/").split("/")[-1]
            doujin_title = item.find("div", "caption").text.strip()
            doujins.append({"code": doujin_code, "title": doujin_title})
        return doujins

    async def get_data(self):
        cin_url = f"{self.cin_url}/g/{self.code}"
        content = await AioHttp.request(
            cin_url, headers={"User-Agent": random.choice(user_agents)}
        )
        soup = BeautifulSoup(content, "html.parser")
        data = json.loads(soup.find("script", id="__NEXT_DATA__").text)["props"][
            "pageProps"
        ]["data"]

        if data and data.get("ok"):
            title = data["title"]
            self.english_title = title["english"]
            self.japanese_title = title["japanese"]
            self.pretty_title = title["pretty"]
            self.cover_url = f"https://t.nhentai.net/galleries/{data['images']['cover']['t'].split('/t/')[-1]}"
            self.pages = data["num_pages"]

            tag_mapping = {
                "tag": self.tags,
                "artist": self.artists,
                "parody": self.parodies,
                "character": self.characters,
                "language": self.languages,
                "category": self.categories,
            }
            for tag in data["tags"]:
                tag_type = tag_mapping.get(tag["type"])
                if tag_type is not None:
                    tag_type.append(
                        f"#{tag['url'].rstrip('/').split('/')[-1].replace('-', '_')}"
                    )

            for image_url in data["images"]["pages"]:
                image_url = (
                    f"https://i.nhentai.net/galleries/{image_url['t'].split('/i/')[-1]}"
                )
                self.image_urls.append(image_url)

        return self

    async def dl_chapter(self, title, mode, file_pass=None):
        pdf_file = get_path(f"{title}.pdf")
        cbz_file = get_path(f"{title}.cbz")

        headers = {"User-Agent": random.choice(user_agents)}
        headers["Referer"] = self.url

        files = []
        images = []
        mode = mode.lower()
        if "graph" in mode or mode == "all":
            first_res = await AioHttp.request(self.image_urls[0], re_res=True)
            if "nhentai.to" not in self.url and first_res.ok:
                graph_url = await images_to_graph(
                    f"{self.pretty_title} | @Nhentai_Doujins",
                    self.image_urls,
                    author="Nhentai Hub",
                    author_url="https://telegram.dog/Nhentai_Doujins",
                )
            else:
                proxy_image_urls = [
                    f"{proxy_url}?src={url}&referer={self.url}"
                    for url in self.image_urls
                ]
                graph_url = await images_to_graph(
                    f"{self.pretty_title} | @Nhentai_Doujins",
                    proxy_image_urls,
                    author="Nhentai Hub",
                    author_url="https://telegram.dog/Nhentai_Doujins",
                )
            files.append(graph_url)

        if "pdf" in mode or mode in ("both", "all"):
            if not images:
                images, temp_dir = await _BASE.download_images(
                    self.image_urls, headers=headers, sequentially=True
                )
            pdf_file = get_path(f"{title}.pdf")
            author = "t.me/Nhentai_Doujins"
            try:
                await imgtopdf(pdf_file, images, author=author)
            except Exception:
                await images_to_pdf(pdf_file, images, author=author)

            if file_pass:
                pdf_file = encrypt_pdf(pdf_file, file_pass)
            files.append(pdf_file)

        if "cbz" in mode or mode in ("both", "all"):
            if not images:
                images, temp_dir = await _BASE.download_images(
                    self.image_urls, headers=headers, sequentially=True
                )
            cbz_file = get_path(f"{title}.cbz")
            pyminizip.compress_multiple(images, [], str(cbz_file), file_pass, 9)
            files.append(cbz_file)

        if images:
            shutil.rmtree(temp_dir)

        return files[0] if len(files) == 1 else files
