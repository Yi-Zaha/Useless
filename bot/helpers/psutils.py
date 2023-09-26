import re

import cloudscraper

from bot.utils.functions import get_link

PS_SITES = {
    "-18": "https://manhwa18.cc/webtoon/",
    "-mc": "https://manhwaclub.net/manga/",
    "-mh": "https://manhwahentai.me/webtoon/",
    "-ws": "https://webtoonscan.com/manhwa/",
    "-m": "https://manhwahub.net/webtoon/",
    "-t": "https://toonily.com/webtoon/",
    "-t3z": "https://hentai3z.com/manga/",
    "-t6": "https://toon69.com/manga/",
    "-md": "https://mangadistrict.com/read-scan/",
}


def quote_clean(name):
    """Replace characters in the name with hyphens."""
    return re.sub(r"[',’?,!]", "", name.lower().replace(" ", "-"))


def zeroint(inp):
    return f"0{inp}" if len(str(inp)) == 1 else inp


async def ps_link(site, name, chapter=None):
    """Generate the link for a given site, name, and chapter."""
    base = PS_SITES.get(site)
    if not base:
        raise ValueError(f"Invalid Site - {site!r}")

    link = base + quote_clean(name)
    link = (await get_link(link, cloud=True)).url

    if chapter:
        if site == "-ws":
            link += f"/{chapter}"
        else:
            link += (
                f"/chapter-{chapter}"
                if not link.endswith("/")
                else f"chapter-{chapter}"
            )
    return link


def iargs(site):
    """Return the class and src attributes based on the site."""
    _class = "wp-manga-chapter-img"
    src = "src"

    if site == "-m":
        _class = "chapter-img img-responsive"
    elif site == "-18":
        _class = re.compile("p*")
    elif site == "-t":
        src = "data-src"

    return {"_class": _class, "src": src}


def ch_from_url(url: str) -> str:
    last_part = url.rstrip("/").split("/")[-1]
    ch_part = last_part.replace("chapter-", "")
    ch = ch_part.replace("-", ".")

    try:
        float(ch)
        return ch
    except ValueError:
        pass

    numRegex = re.compile(r"(\d+(\.\d+)?)")
    match = numRegex.search(ch)
    if match:
        if "chap" in last_part:
            return match.group()

    if "?tachiyomi=true" in url:
        data = cloudscraper.CloudScraper().get(url).json()["chapter"]
        if data["chap"]:
            return data["chap"]
        if data["vol"]:
            return f'Vol - {data["vol"]}'
        if data["title"]:
            return data["title"]

    return ch_part.replace("-", " ").title()
