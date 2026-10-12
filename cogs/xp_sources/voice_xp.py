"""Award XP for time spent in voice with at least one other human.

Every minute, scan all guild voice channels. For each member who is in a
channel with >=1 other non-bot human, credit XP_PER_MINUTE XP, up to
DAILY_MINUTES_CAP per UTC day.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands, tasks

from config import GUILD_ID as _GUILD_ID
from cogs._shared import dev_mode, xp_store
from cogs._shared.json_store import load_json, save_json

logger = logging.getLogger("VoiceXP")

XP_PER_MINUTE = 3
DAILY_MINUTES_CAP = 180

STATE_FILE = Path(__file__).parent / "voice_daily_state.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# Felles atomisk lagring (se cogs/_shared/json_store.py)
_atomic_write = save_json


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return load_json(STATE_FILE, {})
    except Exception as e:
        logger.error(f"Failed to load voice daily_state.json: {e}")
        return {}


def _save_state(data: dict):
    try:
        _atomic_write(STATE_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save voice daily_state.json: {e}")


def _eligible_in_channel(channel: discord.VoiceChannel) -> list[discord.Member]:
    """Return non-bot, non-deafened members if the channel has >=2 humans."""
    humans = [m for m in channel.members if not m.bot]
    if len(humans) < 2:
        return []
    # Optional stricter check: skip self-deafened members so they don't farm XP
    # while AFK with audio off.
    return [m for m in humans if not (m.voice and m.voice.self_deaf)]


class VoiceXP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tick.start()

    def cog_unload(self):
        self.tick.cancel()

    @tasks.loop(minutes=1)
    async def tick(self):
        guild = self.bot.get_guild(int(_GUILD_ID))
        if guild is None:
            return

        today = _today()
        state = _load_state()
        state = {uid: v for uid, v in state.items() if v.get("date") == today}

        changed = False
        for vc in guild.voice_channels:
            for member in _eligible_in_channel(vc):
                if not dev_mode.is_eligible_member(member):
                    continue
                entry = state.get(str(member.id), {"date": today, "minutes": 0})
                if entry.get("date") != today:
                    entry = {"date": today, "minutes": 0}
                if entry["minutes"] >= DAILY_MINUTES_CAP:
                    state[str(member.id)] = entry
                    continue
                try:
                    await xp_store.add_xp(member.id, "voice_xp", XP_PER_MINUTE)
                except Exception as e:
                    logger.error(f"Failed to add voice XP for {member.id}: {e}")
                    continue
                entry["minutes"] += 1
                state[str(member.id)] = entry
                changed = True

        if changed:
            _save_state(state)

    @tick.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceXP(bot))
