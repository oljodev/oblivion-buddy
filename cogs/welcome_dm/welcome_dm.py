import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord.ext import commands

from config import GUILD_ID as _GUILD_ID, Channel
from cogs._shared.json_store import load_json, save_json

logger = logging.getLogger("WelcomeDM")

DELAY_SECONDS = 10 * 60

PENDING_FILE = Path(__file__).parent / "pending.json"


# Felles atomisk lagring (se cogs/_shared/json_store.py)
_atomic_write = save_json


def _load_pending() -> dict:
    try:
        if not PENDING_FILE.exists():
            return {}
        return load_json(PENDING_FILE, {})
    except Exception as e:
        logger.error(f"Failed to load pending.json: {e}")
        return {}


def _save_pending(data: dict):
    try:
        _atomic_write(PENDING_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save pending.json: {e}")


def _build_dm_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Welcome to the server! 👋",
        description=(
            "Glad to have you here. We're a small Minecraft SMP community — "
            "sometimes things are quiet for a bit, but there's a real group of "
            "people behind it and we'd love for you to stick around.\n\n"
            f"If you want to play on the SMP, check out <#{int(Channel.HOW_TO_JOIN)}> "
            "for instructions.\n\n"
            "When you're ready, please run **`/link`** in the server to connect "
            "your Minecraft account — it unlocks playtime tracking, giveaway "
            "auto-entry, and other goodies.\n\n"
            "Hope to see you in the server soon!"
        ),
        color=discord.Color.blurple(),
    )
    return embed


class WelcomeDM(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._tasks: dict[int, asyncio.Task] = {}

    async def cog_load(self):
        # Re-arm pending DMs from JSON after a restart.
        data = _load_pending()
        for user_id_str, entry in list(data.items()):
            try:
                user_id = int(user_id_str)
                scheduled_for = datetime.fromisoformat(entry["scheduled_for"])
            except (KeyError, ValueError) as e:
                logger.error(f"Bad pending entry {user_id_str}: {e}; dropping.")
                data.pop(user_id_str, None)
                _save_pending(data)
                continue
            self._spawn_task(user_id, scheduled_for)
        if self._tasks:
            logger.info(f"Re-armed {len(self._tasks)} pending welcome DM(s).")

    async def cog_unload(self):
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()

    def _spawn_task(self, user_id: int, scheduled_for: datetime):
        task = asyncio.create_task(self._wait_and_send(user_id, scheduled_for))
        self._tasks[user_id] = task

    def _cancel_and_forget(self, user_id: int):
        task = self._tasks.pop(user_id, None)
        if task is not None:
            task.cancel()
        data = _load_pending()
        if str(user_id) in data:
            data.pop(str(user_id))
            _save_pending(data)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        if member.guild.id != int(_GUILD_ID):
            return

        scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=DELAY_SECONDS)
        data = _load_pending()
        data[str(member.id)] = {
            "guild_id": member.guild.id,
            "scheduled_for": scheduled_for.isoformat(),
        }
        _save_pending(data)
        self._spawn_task(member.id, scheduled_for)
        logger.info(
            f"Scheduled welcome DM for {member} (id={member.id}) at {scheduled_for.isoformat()}"
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.id in self._tasks or str(member.id) in _load_pending():
            self._cancel_and_forget(member.id)
            logger.info(
                f"Cancelled welcome DM for {member} (id={member.id}): user left."
            )

    async def _wait_and_send(self, user_id: int, scheduled_for: datetime):
        try:
            delay = (scheduled_for - datetime.now(timezone.utc)).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)

            # Re-check persisted state — user may have spoken/left during the sleep.
            data = _load_pending()
            if str(user_id) not in data:
                return

            guild = self.bot.get_guild(int(_GUILD_ID))
            if guild is None:
                logger.warning(f"Guild {_GUILD_ID} not available; skipping DM for {user_id}.")
                return
            member = guild.get_member(user_id)
            if member is None:
                logger.info(f"User {user_id} no longer in guild; skipping DM.")
                self._cancel_and_forget(user_id)
                return

            try:
                await member.send(embed=_build_dm_embed())
                logger.info(f"Sent welcome DM to {member} (id={user_id}).")
            except discord.Forbidden:
                logger.info(f"Cannot DM {member} (id={user_id}): DMs disabled.")
            except Exception as e:
                logger.error(f"Failed to DM {member} (id={user_id}): {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in _wait_and_send for {user_id}: {e}")
        finally:
            # Clean up state. _cancel_and_forget is idempotent.
            data = _load_pending()
            if str(user_id) in data:
                data.pop(str(user_id))
                _save_pending(data)
            self._tasks.pop(user_id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeDM(bot))
