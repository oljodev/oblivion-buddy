import json
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord.ext import commands, tasks
from aiomcrcon import Client

# reuse RCON & status channel defaults from status.py (same folder)
from .status import RCON_IP, RCON_PORT, RCON_PASS  # STATUS_CHANNEL_ID no longer used

# Use the channel ID you specified
STAFF_PLAYTIME_CHANNEL_ID = 1439871354081116300

# Interval in seconds between checks and increments
CHECK_INTERVAL = 60  # 1 minute

# Keep history for up to 30 days (in seconds)
MAX_HISTORY_SECONDS = 30 * 24 * 3600  # 30 days

# Data file (one JSON object per line, date -> seconds)
DATA_FILE = Path(__file__).parent / "staff_playtime.jsonl"


class StaffPlaytimeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # deque of tuples (timestamp: datetime, seconds: int)
        self.history = deque()
        # daily aggregates loaded from file: { "YYYY-MM-DD": seconds }
        self.daily = {}
        self.playtime_message = None

        # load existing daily data
        self._load_daily_data()

        self.update_task.start()

    def cog_unload(self):
        self.update_task.cancel()

    def _load_daily_data(self):
        """Load the daily JSON-lines file into self.daily"""
        self.daily = {}
        try:
            if DATA_FILE.exists():
                with DATA_FILE.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            date = obj.get("date")
                            secs = int(obj.get("seconds", 0))
                            if date:
                                self.daily[date] = secs
                        except Exception:
                            continue
        except Exception:
            # best-effort load; ignore errors
            pass

    def _save_daily_data(self):
        """Write self.daily to DATA_FILE as JSON-lines (one date per line)."""
        try:
            # keep only last 30 days in file
            cutoff_date = (datetime.now().date() - timedelta(days=30)).isoformat()
            items = sorted((d, s) for d, s in self.daily.items() if d >= cutoff_date)
            with DATA_FILE.open("w", encoding="utf-8") as f:
                for date, secs in items:
                    json.dump({"date": date, "seconds": secs}, f)
                    f.write("\n")
        except Exception:
            pass

    def _purge_old(self, now: datetime):
        """Purge old history samples older than MAX_HISTORY_SECONDS and daily entries older than 30 days."""
        limit = now - timedelta(seconds=MAX_HISTORY_SECONDS)
        while self.history and self.history[0][0] < limit:
            self.history.popleft()

        # purge daily keys older than 30 days
        cutoff = (now.date() - timedelta(days=30)).isoformat()
        keys = list(self.daily.keys())
        for k in keys:
            if k < cutoff:
                self.daily.pop(k, None)

    def _seconds_in_window(self, now: datetime, window_seconds: int) -> int:
        cutoff = now - timedelta(seconds=window_seconds)
        total = 0
        for ts, secs in reversed(self.history):
            if ts < cutoff:
                break
            total += secs
        return total

    def _format_playtime_field(self, seconds: int, window_hours: int) -> str:
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hrs} hours and {mins} minutes / {window_hours} hours!"

    async def _find_existing_message(self, channel: discord.TextChannel):
        """Look for an existing embed message sent by the bot to edit."""
        async for msg in channel.history(limit=50):
            if msg.author == self.bot.user and msg.embeds:
                emb = msg.embeds[0]
                if emb.title and emb.title.startswith("Staff Playtime"):
                    return msg
        return None

    @tasks.loop(seconds=CHECK_INTERVAL)
    async def update_task(self):
        await self.bot.wait_until_ready()

        channel = self.bot.get_channel(STAFF_PLAYTIME_CHANNEL_ID)
        if not channel:
            print("⚠️ Could not find the staff playtime channel.")
            return

        # Check server using RCON (same pattern as status.py)
        try:
            async with Client(RCON_IP, RCON_PORT, RCON_PASS) as client:
                response = await client.send_cmd("list")
                is_online = True
        except Exception:
            response = None
            is_online = False

        # Determine if any players are online from the response
        any_online = False
        if is_online and response:
            text = response[0] if isinstance(response, tuple) else response
            if ":" in text:
                names_part = text.split(":", 1)[1].strip()
                if names_part:
                    any_online = True
            else:
                if "There are" in text and "of a max of" in text:
                    try:
                        player_count = int(text.split("There are ")[1].split(" of")[0])
                        any_online = player_count > 0
                    except Exception:
                        any_online = False

        now = datetime.now()
        increment = CHECK_INTERVAL if any_online else 0

        # Record the sample for rolling-window calculations
        self.history.append((now, increment))

        # Update today's aggregate in self.daily
        today = now.date().isoformat()
        self.daily.setdefault(today, 0)
        self.daily[today] += increment

        # Purge old entries beyond 30 days
        self._purge_old(now)

        # Persist daily aggregates to file
        self._save_daily_data()

        # Compute totals
        secs_24h = self._seconds_in_window(now, 24 * 3600)
        secs_week = self._seconds_in_window(now, 7 * 24 * 3600)
        secs_month = self._seconds_in_window(now, 30 * 24 * 3600)

        # Format fields
        field_24h = self._format_playtime_field(secs_24h, 24)
        field_week = self._format_playtime_field(secs_week, 7 * 24)
        field_month = self._format_playtime_field(secs_month, 30 * 24)

        embed = discord.Embed(
            title="Staff Playtime — Tracking active server time",
            color=discord.Color.blue(),
            timestamp=now,
        )
        embed.add_field(name="Last 24 hours", value=field_24h, inline=False)
        embed.add_field(name="Last week", value=field_week, inline=False)
        embed.add_field(name="Last month", value=field_month, inline=False)
        embed.set_footer(text="Updated")

        # Find or create message to edit
        if not self.playtime_message:
            self.playtime_message = await self._find_existing_message(channel)

        if self.playtime_message:
            try:
                await self.playtime_message.edit(embed=embed)
            except Exception:
                self.playtime_message = None
        else:
            try:
                self.playtime_message = await channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ Failed to send staff playtime embed: {e}")

    @update_task.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(StaffPlaytimeCog(bot))
