from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pyrogram import types

from bot.config import Config
from bot.utils.singleton import Singleton


class DB(AsyncIOMotorCollection, metaclass=Singleton):
    def __init__(self, collection_name: str):
        super().__init__(mongo_db, collection_name)

    async def set_key(self, key, value, exist_ok=False):
        if not exist_ok:
            await self.del_key(key)
        return await self.insert_one({key: value})

    async def update_key(self, key, value, many=False, upsert=False):
        query = {key: {"$exists": 1}}
        new_doc = {key: value}
        update_method = self.update_many if many else self.update_one
        return await update_method(query, {"$set": new_doc}, upsert=upsert)

    async def get_key(self, key, value=None, re_doc=False):
        query = {key: {"$exists": 1}}
        if value:
            query = {key: value}
        doc = await self.find_one(query)
        return doc if re_doc else doc.get(key) if doc else None

    async def del_key(self, key, value=None, many=True):
        query = {key: {"$exists": 1}}
        if value:
            query = {key: value}
        method = self.delete_many if many else self.delete_one
        return await method(query)

    async def insert_data(self, query, extra=None):
        if extra is None:
            extra = {}
        extra = extra or {}
        doc = {**query, **extra}
        await self.update_one(query, {"$set": extra}, upsert=True)
        return doc


class UserDB(DB):
    def __init__(self):
        super().__init__("Users")

    async def add_user(self, user: types.User):
        query = {"id": user.id}
        extra = {
            "name": " ".join(filter(None, [user.first_name, user.last_name])),
            "username": user.username,
        }
        return await self.insert_data(query, extra=extra)

    async def rm_user(self, user_id: int):
        return await self.del_key("id", user_id)


class PSDB(DB):
    def __init__(self):
        super().__init__("PSubs")

    async def add_sub(
        self,
        ps,
        url,
        chat_id,
        title,
        send_updates=False,
        notifs_chat=None,
        file_mode=None,
        custom_filename=None,
        custom_caption=None,
        thumb_url=None,
        file_pass=None,
    ):
        query = {"__name__": "subscription", "ps": ps, "url": url, "chat": chat_id}
        extra = {"title": title}
        if send_updates:
            extra["send_updates"] = bool(send_updates)
        if notifs_chat:
            extra["notifs_chat"] = notifs_chat
        if file_mode:
            extra["file_mode"] = file_mode
        if custom_filename:
            extra["custom_filename"] = custom_filename
        if custom_caption:
            extra["custom_caption"] = custom_caption
        if thumb_url:
            extra["custom_thumb"] = thumb_url
        if file_pass:
            extra["file_pass"] = file_pass
        return await self.insert_data(query, extra=extra)

    async def get_sub(self, ps=None, url=None, chat_id=None, fetch_all=None):
        if ps is None:
            ps = {"$exists": 1}
        if url is None:
            url = {"$exists": 1}
        if chat_id is None:
            chat_id = {"$exists": 1}
        query = {"__name__": "subscription", "ps": ps, "url": url, "chat": chat_id}
        return self.find(query) if fetch_all else await self.find_one(query)

    async def rm_sub(self, ps, url, chat_id):
        query = {"ps": ps, "url": url, "chat": chat_id}
        return await self.delete_many(query)

    def all_subs(self, query={}, **kwargs):
        return self.find({"__name__": "subscription", **query}, **kwargs)

    async def add_lc(self, url, lc_url):
        query = {
            "__name__": "last_chapter",
            "url": url,
        }
        extra = {"lc_url": lc_url}
        return await self.insert_data(query, extra=extra)

    async def get_lc(self, url):
        query = {"__name__": "last_chapter", "url": url}
        return await self.find_one(query)

    async def rm_lc(self, url):
        query = {"__name__": "last_chapter", "url": url}
        return await self.delete_many(query)

    def all_lcs(self, query={}, **kwargs):
        return self.find({"__name__": "last_chapter", **query}, **kwargs)


# Initialize the MongoDB client and database
mongo_client = AsyncIOMotorClient(Config.MONGO_URL)
mongo_db = mongo_client["TESTDB"]
dB = DB("MAIN")
udB = UserDB()
pdB = PSDB()
