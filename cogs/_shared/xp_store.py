"""Shared XP storage helpers.

All XP fields live in ./cogs/simple_stats/user_data/{user_id}.json.

Today's known fields (in addition to ones written by simple_stats/user_stats.py):
  messages_sent       — chat messages (10 XP each)
  invite_xp           — bonus from invite_rewards (raw XP, not a count)
  playtime_xp         — Minecraft playtime XP
  voice_xp            — voice channel XP
  daily_login_xp      — daily login bonus accumulated
  achievement_xp      — Minecraft advancement XP

Reads/writes from new cogs go through here so they share an asyncio lock and
all use atomic file writes.
"""

import asyncio
import json
import logging
import os
import tempfile

logger = logging.getLogger("XPStore")

DATA_FOLDER = "./cogs/simple_stats/user_data"
XP_PER_MESSAGE = 10

XP_FIELDS = (
    "invite_xp",
    "playtime_xp",
    "voice_xp",
    "daily_login_xp",
    "achievement_xp",
)

_lock = asyncio.Lock()


def _user_path(discord_id: int) -> str:
    return os.path.join(DATA_FOLDER, f"{discord_id}.json")


def _load(discord_id: int) -> dict:
    path = _user_path(discord_id)
    base = {"user_id": discord_id, "messages_sent": 0}
    for f in XP_FIELDS:
        base[f] = 0
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            base.update(data)
        except Exception as e:
            logger.error(f"Failed to load {path}: {e}")
    return base


def _save_atomic(discord_id: int, data: dict):
    os.makedirs(DATA_FOLDER, exist_ok=True)
    path = _user_path(discord_id)
    fd, tmp = tempfile.mkstemp(prefix=f"{discord_id}.", suffix=".json.tmp", dir=DATA_FOLDER)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_user_stats(discord_id: int) -> dict:
    """Return the full per-user stats dict (with all known XP fields)."""
    return _load(discord_id)


def get_total_xp(stats: dict) -> int:
    return (
        stats.get("messages_sent", 0) * XP_PER_MESSAGE
        + stats.get("invite_xp", 0)
        + stats.get("playtime_xp", 0)
        + stats.get("voice_xp", 0)
        + stats.get("daily_login_xp", 0)
        + stats.get("achievement_xp", 0)
    )


async def add_xp(discord_id: int, field: str, amount: int) -> int:
    """Atomically add `amount` XP to `field` for `discord_id`. Returns new value."""
    if field not in XP_FIELDS:
        raise ValueError(f"Unknown XP field: {field}")
    if amount == 0:
        return _load(discord_id).get(field, 0)
    async with _lock:
        data = _load(discord_id)
        data[field] = data.get(field, 0) + amount
        _save_atomic(discord_id, data)
        return data[field]
