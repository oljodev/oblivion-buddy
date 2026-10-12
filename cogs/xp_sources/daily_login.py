"""Daily login bonus + streak tracking.

When a linked player is detected online for the first time on a new UTC day,
award `100 + min(streak * 20, 200)` XP and increment their streak. Missing a
day resets the streak to 1 on next login.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import GUILD_ID as _GUILD_ID
from cogs._shared import dev_mode, mc_online, xp_store
from cogs._shared.json_store import load_json, save_json

logger = logging.getLogger("DailyLogin")

GUILD_ID = discord.Object(id=_GUILD_ID)

POLL_MINUTES = 5
BASE_BONUS = 100
PER_STREAK_DAY = 20
MAX_STREAK_BONUS = 200

STATE_FILE = Path(__file__).parent / "daily_login_state.json"


def _today() -> date:
    return datetime.now(timezone.utc).date()


# Felles atomisk lagring (se cogs/_shared/json_store.py)
_atomic_write = save_json


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return load_json(STATE_FILE, {})
    except Exception as e:
        logger.error(f"Failed to load daily_login state: {e}")
        return {}


def _save_state(data: dict):
    try:
        _atomic_write(STATE_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save daily_login state: {e}")


def _bonus_for_streak(streak: int) -> int:
    return BASE_BONUS + min(streak * PER_STREAK_DAY, MAX_STREAK_BONUS)


class DailyLogin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll.start()

    def cog_unload(self):
        self.poll.cancel()

    @tasks.loop(minutes=POLL_MINUTES)
    async def poll(self):
        try:
            online = await mc_online.get_online_linked()
        except Exception as e:
            logger.debug(f"mc_online lookup failed: {e}")
            return
        if not online:
            return

        today = _today()
        today_str = today.isoformat()
        yesterday_str = (today - timedelta(days=1)).isoformat()
        state = _load_state()
        changed = False

        for discord_id, mc_name in online:
            if not dev_mode.is_eligible_id(self.bot, discord_id):
                continue
            entry = state.get(str(discord_id), {})
            last_login = entry.get("last_login_date")
            if last_login == today_str:
                continue  # already credited today

            if last_login == yesterday_str:
                streak = entry.get("streak", 0) + 1
            else:
                streak = 1

            best_streak = max(entry.get("best_streak", 0), streak)
            bonus = _bonus_for_streak(streak)

            try:
                await xp_store.add_xp(discord_id, "daily_login_xp", bonus)
            except Exception as e:
                logger.error(f"Failed to add daily login XP for {discord_id}: {e}")
                continue

            entry.update(
                {
                    "last_login_date": today_str,
                    "streak": streak,
                    "best_streak": best_streak,
                }
            )
            state[str(discord_id)] = entry
            changed = True
            logger.info(
                f"Daily login bonus +{bonus} XP to discord={discord_id} mc={mc_name} "
                f"streak={streak}"
            )

            user = self.bot.get_user(discord_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(discord_id)
                except Exception:
                    user = None
            if user is not None:
                embed = discord.Embed(
                    title="🔥 Daily login bonus",
                    description=(
                        f"Day **{streak}** of your streak — **+{bonus} XP**!\n\n"
                        f"Best streak: **{best_streak} days**"
                    ),
                    color=discord.Color.orange(),
                )
                try:
                    await user.send(embed=embed)
                except discord.Forbidden:
                    pass
                except Exception as e:
                    logger.debug(f"Could not DM {discord_id}: {e}")

        if changed:
            _save_state(state)

    @poll.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="streak", description="Show your current daily login streak."
    )
    @app_commands.guilds(GUILD_ID)
    async def streak(self, interaction: discord.Interaction):
        state = _load_state()
        entry = state.get(str(interaction.user.id))
        if not entry:
            return await interaction.response.send_message(
                "You don't have a streak yet — log into the SMP to start one!",
                ephemeral=True,
            )

        today_str = _today().isoformat()
        yesterday_str = (_today() - timedelta(days=1)).isoformat()
        last = entry.get("last_login_date")
        active = last in (today_str, yesterday_str)
        streak = entry.get("streak", 0) if active else 0

        embed = discord.Embed(
            title="🔥 Daily login streak",
            color=discord.Color.orange() if active else discord.Color.dark_gray(),
        )
        embed.add_field(name="Current", value=f"**{streak}** days", inline=True)
        embed.add_field(
            name="Best", value=f"**{entry.get('best_streak', 0)}** days", inline=True
        )
        embed.add_field(name="Last login", value=last or "—", inline=True)
        if active:
            next_bonus = _bonus_for_streak(streak + 1)
            embed.set_footer(text=f"Tomorrow's bonus: {next_bonus} XP")
        else:
            embed.set_footer(text="Streak will reset to 1 on your next login.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyLogin(bot))
