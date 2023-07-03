import asyncio
from bot.utils.functions import post_to_telegraph

_locks = {}


async def download_doujin_files(doujin, file=None):
    file = file or str(doujin.code)
    if doujin not in _locks:
        _locks[doujin.code] = asyncio.Lock()
    async with _locks[doujin.code]:
        pdf, cbz = await doujin.dl_chapter(file, "both")
        return pdf, cbz


async def generate_telegraph_link(doujin):
    graph_link = await post_to_telegraph(
        doujin.title,
        "".join(f"<img src='{url}'/>" for url in doujin.image_urls),
        author="Nhentai Hub",
        author_url="https://telegram.me/Nhentai_Doujins",
    )
    return graph_link


def generate_doujin_info(doujin):
    msg = f"[{doujin.title}]({doujin.read_url})\n"
    msg += f"\n➤ **Code:** {doujin.code}"

    if doujin.categories:
        msg += "\n➤ **Type:** " + " ".join(doujin.categories)

    if doujin.parodies:
        msg += "\n➤ **Parodies:** " + " ".join(doujin.parodies)

    if doujin.artists:
        msg += "\n➤ **Artists:** " + " ".join(doujin.artists)

    if doujin.languages:
        msg += "\n➤ **Languages:** " + " ".join(doujin.languages)

    msg += f"\n➤ **Pages:** {doujin.pages}"

    if doujin.tags:
        msg += "\n➤ **Tags:** " + " ".join(doujin.tags)

    return msg
