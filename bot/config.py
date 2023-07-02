from os import environ

from dotenv import load_dotenv

load_dotenv(".env")


class _Config:
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __getattr__(self, key):
        return self.get(key)

    def __getitem__(self, key):
        value = environ[key]
        try:
            value = int(value)
        except ValueError:
            pass
        return value

    def __setitem__(self, key, value):
        environ[key] = value

    def __repr__(self):
        return str(dict(environ))


Config = _Config()

if not all(
    Config.get(name) for name in ["API_ID", "API_HASH", "BOT_TOKEN", "MONGO_URL"]
):
    exit("Error: Environment is not set.")
