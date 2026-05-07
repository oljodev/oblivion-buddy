"""Award XP for time spent on the Minecraft server.

Polls the shared MC-online helper every PERIOD_MINUTES and credits each
linked online player with PERIOD_MINUTES * XP_PER_MINUTE, capped at
DAILY_MINUTES_CAP minutes per UTC day.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands, tasks

from cogs._shared import dev_mode, mc_online, xp_store

logger = logging.getLogger("PlaytimeXP")

PERIOD_MINUTES = 5
XP_PER_MINUTE = 5
DAILY_MINUTES_CAP = 240

STATE_FILE = Path(__file__).parent / "playtime_daily_state.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _atomic_write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load daily_state.json: {e}")
        return {}


def _save_state(data: dict):
    try:
        _atomic_write(STATE_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save daily_state.json: {e}")


class PlaytimeXP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll.start()

    def cog_unload(self):
        self.poll.cancel()

    @tasks.loop(minutes=PERIOD_MINUTES)
    async def poll(self):
        try:
            online = await mc_online.get_online_linked()
        except Exception as e:
            logger.debug(f"mc_online lookup failed: {e}")
            return
        if not online:
            return

        today = _today()
        state = _load_state()
        # Drop any non-today buckets to keep the file small.
        state = {uid: v for uid, v in state.items() if v.get("date") == today}

        changed = False
        for discord_id, mc_name in online:
            if not dev_mode.is_eligible_id(self.bot, discord_id):
                continue
            entry = state.get(str(discord_id), {"date": today, "minutes": 0})
            if entry.get("date") != today:
                entry = {"date": today, "minutes": 0}
            already = entry["minutes"]
            allowed = max(0, DAILY_MINUTES_CAP - already)
            if allowed <= 0:
                state[str(discord_id)] = entry
                continue
            credit_minutes = min(PERIOD_MINUTES, allowed)
            xp = credit_minutes * XP_PER_MINUTE
            try:
                await xp_store.add_xp(discord_id, "playtime_xp", xp)
            except Exception as e:
                logger.error(f"Failed to add playtime XP for {discord_id} ({mc_name}): {e}")
                continue
            entry["minutes"] = already + credit_minutes
            state[str(discord_id)] = entry
            changed = True
            logger.info(
                f"Playtime XP +{xp} to discord={discord_id} mc={mc_name} "
                f"({entry['minutes']}/{DAILY_MINUTES_CAP} min today)"
            )

        if changed:
            _save_state(state)

    @poll.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(PlaytimeXP(bot))
