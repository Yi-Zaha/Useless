import ast
import asyncio
import html
import os
import json
import random
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from bot import bot
from bot.utils import user_agents
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.functions import get_link, get_soup, retry_func
from bot.utils.pdf import get_path, images_to_pdf, imgtopdf


class IManga:
    def __init__(self, manga_id, nelo=False):
        self.base_url = (
            "https://ww5.manganelo.tv/manga/" if nelo else "https://readmanganato.com/"
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
        url = self.base_url + self.id
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
            self.poster_url = "https://ww5.manganelo.tv" + self.poster_url
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
                link = "https://ww5.manganelo.tv" + link
            data[chapter] = link
        return data

    @staticmethod
    async def dl_chapter(chapter_url, title, mode):
        dir = tempfile.mkdtemp()
        headers = {"User-Agent": random.choice(user_agents)}
        content = await AioHttp.request(chapter_url, headers=headers)
        soup = BeautifulSoup(content, "html.parser")
        headers["Referer"] = chapter_url

        images_list = []
        if "manganato" in chapter_url or "manganelo" in chapter_url:
            images_list = [
                img.get("src") for img in soup.find("div", "container-chapter-reader").find_all("img")
            ]
        elif "mangabuddy" in chapter_url:
            regex = r"var chapImages = '(.*)'"
            images_list = re.findall(regex, soup.prettify())[0].split(",")
        elif "hentai2read" in chapter_url:
            img_base = "https://static.hentai.direct/hentai"
            regex = r"'images' : (.*)"
            images_list = ast.literal_eval(
                re.findall(regex, soup.prettify())[0].strip(",")
            )
            images_list = [img_base + img.replace("\\", "") for img in images_list]
        elif "mangatoto" in chapter_url:
            regex = r"const imgHttpLis = (.*);"
            images_list = ast.literal_eval(re.findall(regex, soup.prettify())[0])
        elif "mangapark" in chapter_url:
            data = json.loads(soup.find("script", id="__NEXT_DATA__").text)
            image_set = data["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]["data"]["imageSet"]
            images_list = [f"{link}?{extra}" for link, extra in zip(image_set["httpLis"], image_set["wordLis"])]

        tasks = []
        images = []
        for index, link in enumerate(images_list):
            ext = os.path.splitext(link)
            ext = ext[1] if len(ext) > 1 else ".jpg"
            filename = f"{dir}/{index}{ext}"
            task = asyncio.create_task(
                retry_func(AioHttp.download(link, filename=filename, headers=headers))
            )
            tasks.append(task)
            images.append(filename)

        await asyncio.gather(*tasks)

        files = []
        if mode.lower() in ("pdf", "both"):
            pdf_file = get_path(title + ".pdf")
            author = f"https://telegram.me/{bot.me.username}"
            try:
                imgtopdf(pdf_file, images, author=author)
            except Exception:
                images_to_pdf(pdf_file, images, author=author)
            files.append(pdf_file)

        if mode.lower() in ("cbz", "both"):
            cbz_file = get_path(title + ".cbz")
            with zipfile.ZipFile(cbz_file, "w") as cbz:
                for image_path in images:
                    cbz.write(image_path, compress_type=zipfile.ZIP_DEFLATED)
            files.append(cbz_file)

        shutil.rmtree(dir)
        return files[0] if len(files) == 1 else files


class PS:
    __all__ = ["Toonily", "Manhwa18", "Manganato", "Mangabuddy"]

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
        else:
            raise ValueError(f"Invalid Ps Link: {link!r}")

    @staticmethod
    def iargs(ps):
        if ps == "Toonily":
            return "-t"
        elif ps == "Manhwa18":
            return "-18"

    @staticmethod
    async def get_title(link, ps=None):
        ps = ps or PS.guess_ps(link)
        bs = await get_soup(link, cloud=True)
        if ps == "Manhwa18":
            return (
                bs.title.string.replace("Read", "")
                .strip()
                .split("Manhwa at")[0]
                .strip()
            )
        elif ps == "Toonily":
            return (
                bs.title.string.replace("Read", "")
                .replace("Manga - Toonily", "")
                .strip()
            )
        elif ps == "Manganato":
            return bs.find(class_="story-info-right").find("h1").text.strip()
        elif ps == "Mangabuddy":
            return bs.find("div", "name box").find("h1").text
        else:
            raise ValueError(f"Invalid Site: {ps!r}")

    @staticmethod
    async def iter_chapters(link, ps=None):
        link = link
        ps = ps or PS.guess_ps(link)
        if ps == "Manhwa18":
            bs = await get_soup(link, cloud=True)
            for item in bs.find_all("a", "chapter-name text-nowrap"):
                yield urljoin("https://manhwa18.cc/", item["href"])
        elif ps == "Toonily":
            bs = await get_soup(link, cloud=True)
            for item in bs.find_all("li", "wp-manga-chapter"):
                yield item.find("a")["href"]
        elif ps == "Manganato":
            manga_id = link.split("/")[-1]
            manga = await IManga(manga_id)._parse_info()
            for ch_url in reversed(manga.chapters.values()):
                yield ch_url
        elif ps == "Mangabuddy":
            base = "https://mangabuddy.com/"
            splited = link.split("/")
            manga_id = splited[-1] or splited[-2]
            link = f"{base}api/manga/{manga_id}/chapters?source=detail"
            bs = await get_soup(link, cloud=True)
            for item in bs.find("ul", id="chapter-list").findAll("li"):
                yield urljoin(base, item.find("a")["href"])
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
            data = dict()
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
            data = dict()
            for item in items:
                manga_url = item.find("a")["href"]
                chapter_url = item.find("div", "chapter-item").find("a")["href"]
                data[manga_url] = chapter_url
        elif ps == "Manganato":
            base = "https://manganato.com/"
            content = await AioHttp.request(base, headers=headers)
            soup = BeautifulSoup(content, "html.parser")
            items = soup.find_all("div", "content-homepage-item")
            data = dict()
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
            data = dict()
            for item in items:
                manga_url = urljoin(base, item.a["href"])
                chapter_item = item.findNext("div", "chap-item")
                if not (chapter_item or chapter_item.a):
                    continue
                chapter_url = urljoin(base, chapter_item.a["href"])
                if manga_url not in data:
                    data[manga_url] = chapter_url
        else:
            raise ValueError(f"Invalid Site: {ps!r}")
        return data

    @staticmethod
    async def dl_chapter(
        chapter_url, title, mode, _class="wp-manga-chapter-img", src="src"
    ):
        headers = {"User-Agent": random.choice(user_agents)}
        response = await get_link(chapter_url, headers=headers, cloud=True)

        content = response.text
        soup = BeautifulSoup(content, "html.parser")

        items = soup.find_all("img", _class)
        if not items:
            raise ValueError

        tmp_dir = tempfile.mkdtemp()
        headers["Referer"] = str(response.url)

        tasks = []
        images = []
        for n, item in enumerate(items):
            link = item.get(src) or item.get("data-src")
            if not link:
                continue
            link = link.strip()
            ext = os.path.splitext(link)
            ext = ext[1] if ext else ".jpg"
            image = os.path.join(tmp_dir, f"{n}{ext}")
            images.append(image)
            task = asyncio.create_task(
                retry_func(AioHttp.download(link, filename=image, headers=headers))
            )
            tasks.append(task)

        try:
            await asyncio.gather(*tasks)
        except BaseException:
            try:
                for task in tasks:
                    await task
            except BaseException:
                shutil.rmtree(tmp_dir)
                raise

        files = []
        if mode.lower() in ("pdf", "both"):
            pdf_file = get_path(title + ".pdf")
            try:
                imgtopdf(pdf_file, images, author="t.me/Adult_Mangas")
            except BaseException:
                images_to_pdf(pdf_file, images, author="t.me/Adult_Mangas")
            files.append(pdf_file)

        elif mode.lower() in ("cbz", "both"):
            cbz_file = get_path(title + ".cbz")
            with zipfile.ZipFile(cbz_file, "w") as cbz:
                for image in images:
                    cbz.write(image, compress_type=zipfile.ZIP_DEFLATED)
            files.append(cbz_file)

        shutil.rmtree(tmp_dir)
        return files[0] if len(files) == 1 else files


class Nhentai:
    async def get(self, link):
        if not link.isdigit():
            link = link
            code_regex = re.findall(r"\d+\.*\d+", link)
            self.code = code_regex[0] if code_regex else "N/A"
        else:
            self.code = link
            link = f"https://nhentai.to/g/{link}/"

        content = await AioHttp.request(link)
        soup = BeautifulSoup(content, "html.parser")
        self.title = soup.find("div", id="info").find("h1").text
        self.tags = []
        self.artists = []
        self.parodies = []
        self.categories = []
        self.languages = []
        self.image_urls = []
        self.read_url = f"{link}1" if link.endswith("/") else f"{link}/1"
        self.url = link

        tag_mapping = {
            "tag": self.tags,
            "artist": self.artists,
            "parody": self.parodies,
            "language": self.languages,
            "category": self.categories,
        }

        tdata = soup.find_all("a", "tag")
        for t in tdata:
            tag_type = next(
                (tag_type for tag_type in tag_mapping if tag_type in t["href"]), None
            )
            if tag_type:
                t = (
                    t.find(class_="name")
                    if any(x in self.url for x in [".xxx", ".net"])
                    else t
                )
                tag_name = (
                    t.text.strip().split("\n")[0].replace(" ", "_").replace("-", "")
                )
                tag_mapping[tag_type].append(f"#{tag_name}")

        data = soup.find_all("img", "lazyload")
        for img in data:
            img_url = (
                img["data-src"]
                .strip()
                .replace("t.", ".")
                .replace("t3.nhentai.net", "i3.nhentai.net")
            )
            if img_url.endswith("/") or img_url.endswith(("thumb.jpg", "cover.jpg")):
                continue
            self.image_urls.append(img_url)

        self.pages = len(self.image_urls)

        return self

    async def dl_chapter(self, title, mode):
        dir = Path("cache/nhentai")
        dir.mkdir(exist_ok=True)
        tmp_dir = dir / str(self.code)
        tmp_dir.mkdir(exist_ok=True)
        pdf_file = get_path(title + ".pdf")
        cbz_file = get_path(title + ".cbz")

        headers = {"User-Agent": random.choice(user_agents)}
        headers["Referer"] = self.url
        tasks = []
        images = []
        for n, url in enumerate(self.image_urls):
            ext = os.path.splitext(url)
            ext = ext[1] if ext else ".png"
            image = tmp_dir / f"{n}{ext}"
            images.append(image)
            task = asyncio.create_task(
                retry_func(AioHttp.download(url, filename=image, headers=headers))
            )
            tasks.append(task)

        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                await task

        files = []
        if mode.lower() in ("pdf", "both"):
            try:
                imgtopdf(pdf_file, images, author="t.me/Nhentai_Doujins")
            except Exception:
                images_to_pdf(pdf_file, images, author="t.me/Nhentai_Doujins")
            files.append(pdf_file)
        if mode.lower() in ("cbz", "both"):
            with zipfile.ZipFile(cbz_file, "w") as cbz:
                for image in images:
                    cbz.write(image, compress_type=zipfile.ZIP_DEFLATED)
            files.append(cbz_file)

        shutil.rmtree(tmp_dir)

        return files[0] if len(files) == 1 else files
