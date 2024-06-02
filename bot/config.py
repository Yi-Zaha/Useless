import json
import os
from typing import Any

from dotenv import find_dotenv, load_dotenv


class _Config:
    """Configuration class for loading and accessing environment variables."""

    def __init__(self):
        """Loads environment variables from a .env file if it exists."""
        if dot_env := find_dotenv():
            load_dotenv(dot_env, override=True)
            os.remove(dot_env)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves the value of an environment variable.

        Args:
            key: The name of the environment variable.
            default: The default value to return if the variable is not set.

        Returns:
            The value of the environment variable, or the default value if it is not set.
        """
        value = os.environ.get(key, default)
        if value is not None:
            try:
                return int(value)
            except ValueError:
                return value
        return value

    def __getattr__(self, key: str) -> Any:
        """Allows accessing environment variables as attributes."""
        return self.get(key)

    def __repr__(self):
        return json.dumps(dict(os.environ), indent=4, ensure_ascii=False)


Config = _Config()

REQUIRED_VARS = ["API_ID", "API_HASH", "BOT_TOKEN", "MONGO_URL"]
UNSET_VARS = []
for name in REQUIRED_VARS:
    if Config.get(name):
        continue
    UNSET_VARS.append(name)
if UNSET_VARS:
    exit(f"Error: Environment variables not set: Set {', '.join(UNSET_VARS)}")
