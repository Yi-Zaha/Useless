import random
from urllib.parse import urljoin

import cloudscraper
from bs4 import BeautifulSoup
from bot.utils import user_agents
from bot.utils.aiohttp_helper import AioHttp
from bot.utils.functions import is_url


CONSUMET_API = random.choice([
    "https://api.consumet.org",
    "https://api-consumet-org-ecru.vercel.app"
])


class GogoAnime:
    base_url = "https://gogoanime.gr"
    ajax_url = "https://ajax.gogo-load.com/ajax/"
    api_url = f"{CONSUMET_API}/anime/gogoanime"

    headers = {
        "User-Agent": random.choice(user_agents)
    }
    cookies = {
        "auth": "aplnqLxgJbgtaoyFayGHsnA8ndd8z0BnmuGGwYwDl8BgPk3udnmsQsbW%2B4jXcmkfayLPOTXcZHip799T%2FTkUyg%3D%3D",
        "gogoanime": "hg9f7phuvd6ccm79k51unu6c62",
    }

    async def latest(self, page: int = 1, type: int = 1):
        """
        Returns a list of latest anime episodes.
        """
        latest_url = f"{self.ajax_url}/page-recent-release.html?page={page}&type={type}"

        content = await AioHttp.request(latest_url, headers=self.headers)

        return self._recent_episodes_from_page(content)

    async def popular(self, page: int = 1):
        """
        Returns a list of popular/trending anime.
        """
        popular_url = f"{self.base_url}/popular.html?page={page}"

        content = await AioHttp.request(popular_url, headers=self.headers)

        return self._animes_from_page(content)

    async def search(self, query: str, page: int):
        """
        Returns a list of anime filtered by a query.
        """
        search_url = f"{self.base_url}/search.html?keyword={query}&page={page}"

        content = await AioHttp.request(search_url, headers=self.headers)

        return self._animes_from_page(content)

    async def get_anime(self, anime_id: str):
        """
        Returns info about an anime.
        """
        url = f"{self.api_url}/info/{anime_id}"

        data = {}
        try:
            data = await AioHttp.request(url, re_json=True, headers=self.headers)
            assert data["id"]
        except (AssertionError, KeyError):
            pass
        except Exception as e:
            print(e)

        return data

    async def get_episode_stream_urls(self, episode_id: str):
        """
        Returns m3u8 stream URLs of an episode.
        """
        url = f"{self.api_url}/watch/{episode_id}"

        data = {}
        try:
            data = await AioHttp.request(url, headers=self.headers)
            assert data["sources"]
        except (AssertionError, KeyError):
            pass
        except Exception as e:
            print(e)

        return data

    async def get_episode_servers(self, episode_url: str = None, episode_id: str = None):
        """
        Returns all mirror URLs and download URLs of an episode.
        """
        if episode_url is None:
            if episode_id:
                episode_url = urljoin(self.base_url, episode_id)
            else:
                return

        content = await AioHttp.request(episode_url, headers=self.headers, cookies=self.cookies)

        soup = BeautifulSoup(content, "html.parser")

        multi_container = soup.find("div", "anime_muti_link")
        multi_items = multi_container.find_all("li") if multi_container else []

        dl_container = soup.find("div", "cf-download")
        dl_items = dl_container.find_all("a") if dl_container else []

        mirror_urls = {}
        for item in multi_items:
            mirror = item.text.replace(item.span.text, "").strip()
            link = item.a["data-video"]
            url = "https:" + link if not link.startswith("http") else link
            mirror_urls[mirror] = url
        dl_urls = {
            item.text.strip().split("x")[1] + "p": item["href"]
            for item in dl_items
        }

        return mirror_urls, dl_urls

    def _animes_from_page(self, content: bytes):
        soup = BeautifulSoup(content, "html.parser")

        items = soup.find("ul", "items").find_all("li")

        results = []
        for item in items:
            anime_item = item.find("p", "name").find("a")
            anime_name = anime_item.text.strip()
            anime_id = anime_item["href"].split("/")[-1]
            results.append({"title": anime_name, "id": anime_id})

        pagination = soup.find("div", "pagination")
        total_pages = int(pagination.find_all("a")[-1].text.strip()) if pagination else 1
        has_next_page = page < total_pages

        return {
            "results": results,
            "has_next_page": has_next_page
        }

    def _recent_episodes_from_page(self, content: bytes):
        soup = BeautifulSoup(content, "html.parser")

        items = soup.find("ul", "items").find_all("li")

        results = []
        for item in items:
            anime_item = item.find("p", "name").find("a")
            anime_name = anime_item.text.strip()
            episode = item.find("p", "episode").text.strip()
            episode_id = anime_item["href"].lstrip("/")
            episode_url = urljoin(self.base_url, episode_id)
            image = item.find("img")["src"]
            results.append({
                "title": anime_name,
                "episode": episode,
                "id": episode_id,
                "url": episode_url,
                "image": image,
            })

        pagination = soup.find("div", "pagination")
        total_pages = int(pagination.find_all("a")[-1].text.strip()) if pagination else 1
        has_next_page = page < total_pages

        return {
            "results": results,
            "has_next_page": has_next_page
        }