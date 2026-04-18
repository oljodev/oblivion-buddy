import os
import json
import logging
import re
from datetime import datetime, timezone
from aiomcrcon import Client
import discord
from discord.ext import commands, tasks

RCON_IP = os.getenv("RCON_IP", "localhost")
RCON_PORT = int(os.getenv("RCON_PORT", 25575))
RCON_PASSWORD = os.getenv("RCON_PASS", "secret")

logger = logging.getLogger(__name__)

from channels import LOG_CHANNEL as LOG_CHANNEL_ID, SIMPLE_STATS_CHANNEL as STATS_CHANNEL_ID

# Words that might appear in RCON response that are NOT names
BLACKLIST_NAMES = {
    "there",
    "are",
    "of",
    "a",
    "max",
    "players",
    "online",
    "server",
    "info",
    "list",
    "connected",
    "max",
    "joined",
    "left",
}


class PlayersOnline(commands.Cog):
    """Cog that polls Minecraft RCON for online players and updates a persistent embed."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        base = os.path.dirname(__file__)
        self.storage_path = os.path.join(base, "players_online.json")
        self._ensure_storage()
        self._load_storage()
        self.poll_task.start()

    def cog_unload(self):
        self.poll_task.cancel()

    def _ensure_storage(self):
        dirpath = os.path.dirname(self.storage_path)
        if not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "message_id": 0,
                        "players": {},
                        "announced_milestones": [],
                        "announced_last24_milestones": [],
                        "announced_last72_milestones": [],
                        "announced_last7d_milestones": [],
                        "announced_last14d_milestones": [],
                        "playtime_log": [],
                    },
                    f,
                )

    def _load_storage(self):
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self.storage = json.load(f)
        except Exception:
            self.storage = {"message_id": 0, "players": {}}

        self.storage.setdefault("message_id", 0)
        self.storage.setdefault("players", {})
        self.storage.setdefault("announced_milestones", [])
        self.storage.setdefault("announced_last24_milestones", [])
        self.storage.setdefault("announced_last72_milestones", [])
        self.storage.setdefault("announced_last7d_milestones", [])
        self.storage.setdefault("announced_last14d_milestones", [])
        self.storage.setdefault("playtime_log", [])

    def _save_storage(self):
        tmp = self.storage_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.storage, f, indent=2)
        os.replace(tmp, self.storage_path)

    async def _rcon_list(self):
        """Run 'list' via aiomcrcon.Client."""
        try:
            async with Client(RCON_IP, RCON_PORT, RCON_PASSWORD) as client:
                resp = await client.send_cmd("list")
                if isinstance(resp, (tuple, list)):
                    return "\n".join(map(str, resp))
                return str(resp) if resp is not None else None
        except Exception:
            logger.exception("RCON error")
            return None

    def _parse_list_response(self, resp: str):
        """
        Parses the Minecraft 'list' command.
        Target format: "There are 2/20 players online: Alice, Bob"
        """
        if not resp:
            return []

        # 1. Attempt to find the list part after the colon
        # Matches: "... players online: name1, name2"
        match = re.search(r"online:?\s*(.*)", resp, re.IGNORECASE)

        raw_names_str = ""
        if match:
            raw_names_str = match.group(1)
        else:
            # Fallback: if no colon usage found, assume specific Bungee/Velocity output
            # or try to process the whole string if it's just a raw list
            raw_names_str = resp

        # 2. Split by comma or whitespace
        tokens = re.split(r"[,\s]+", raw_names_str)

        valid_names = []
        for t in tokens:
            # Strip non-alphanumeric chars (punctuation)
            clean_name = re.sub(r"^[^A-Za-z0-9_]+|[^A-Za-z0-9_]+$", "", t)

            # Validation:
            # 1. Length 2-16 (standard MC, some servers allow longer, adjusting to 20)
            # 2. Must not be just numbers (avoids IDs/timestamps)
            # 3. Must not be in blacklist words
            if (
                2 <= len(clean_name) <= 20
                and not clean_name.isdigit()
                and clean_name.lower() not in BLACKLIST_NAMES
            ):
                valid_names.append(clean_name)

        # Remove duplicates while preserving order
        seen = set()
        uniq = []
        for n in valid_names:
            if n.lower() not in seen:
                seen.add(n.lower())
                uniq.append(n)
        return uniq

    def _categorize_players(self):
        now = datetime.now(timezone.utc).timestamp()
        players = self.storage.get("players", {}) or {}
        last24 = []
        last72 = []
        last7d = []
        last14d = []
        all_time = []

        for name, ts in players.items():
            all_time.append(name)
            try:
                age_hours = (now - float(ts)) / 3600.0
                if age_hours <= 24:
                    last24.append(name)
                if age_hours <= 72:
                    last72.append(name)
                if age_hours <= 168:
                    last7d.append(name)
                if age_hours <= 336:
                    last14d.append(name)
            except ValueError:
                continue

        def sort_nocase(lst):
            return sorted(lst, key=lambda s: s.lower())

        return sort_nocase(last24), sort_nocase(last72), sort_nocase(last7d), sort_nocase(last14d), sort_nocase(all_time)

    def _get_next_milestone(self, current_count):
        """Get the next milestone if current_count has reached one (50, 75, 100, 125, ...)"""
        for milestone in range(50, current_count + 1, 25):
            if current_count >= milestone:
                return milestone
        return None

    def _get_next_10_milestone(self, current_count):
        """Get the next 10-player milestone if current_count has reached one (10, 20, 30, 40, 50, ...)"""
        for milestone in range(10, current_count + 1, 10):
            if current_count >= milestone:
                return milestone
        return None

    def _build_embed(self):
        now = datetime.now(timezone.utc)
        embed = discord.Embed(
            title="Players Online",
            description="Recent activity on the server.",
            colour=discord.Colour.green(),
            timestamp=now,
        )
        last24, last72, last7d, last14d, all_time = self._categorize_players()

        # Use comma separation instead of newlines to save space
        def fmt(names):
            if not names:
                return "None"
            # If list is too long, truncate it to avoid Discord Embed limits (1024 chars)
            text = ", ".join(names)
            if len(text) > 1000:
                return text[:997] + "..."
            return text

        embed.add_field(
            name=f"Last 24 Hours ({len(last24)})", value=fmt(last24), inline=False
        )
        embed.add_field(
            name=f"Last 72 Hours ({len(last72)})", value=fmt(last72), inline=False
        )
        embed.add_field(
            name=f"Last 7 Days ({len(last7d)})", value=fmt(last7d), inline=False
        )
        embed.add_field(
            name=f"Last 14 Days ({len(last14d)})", value=fmt(last14d), inline=False
        )
        embed.add_field(
            name=f"All Time Unique ({len(all_time)})", value=fmt(all_time), inline=False
        )

        embed.set_footer(text="Auto-updates every 15 minutes")
        return embed

    async def _send_milestone_announcement(self, milestone_count, category="all_time"):
        """Send an embed to the LOG channel announcing a new milestone.

        Args:
            milestone_count: The player count that was reached
            category: Type of milestone - 'all_time', 'last24', or 'last72'
        """
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if not channel:
            logger.warning(f"LOG channel {LOG_CHANNEL_ID} not found")
            return

        # Customize the embed based on category
        if category == "last24":
            title = "🎉 Last 24 Hours Milestone Reached!"
            description = f"The server has had **{milestone_count}** unique players in the last 24 hours!"
        elif category == "last72":
            title = "🎉 Last 72 Hours Milestone Reached!"
            description = f"The server has had **{milestone_count}** unique players in the last 72 hours!"
        elif category == "last7d":
            title = "🎉 Last 7 Days Milestone Reached!"
            description = f"The server has had **{milestone_count}** unique players in the last 7 days!"
        elif category == "last14d":
            title = "🎉 Last 14 Days Milestone Reached!"
            description = f"The server has had **{milestone_count}** unique players in the last 14 days!"
        else:  # all_time
            title = "🎉 Unique Players Milestone Reached!"
            description = (
                f"The server has reached **{milestone_count}** all-time unique players!"
            )

        embed = discord.Embed(
            title=title,
            description=description,
            colour=discord.Colour.gold(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Oblivion Buddy Milestone Tracker")

        try:
            await channel.send(embed=embed)
            logger.info(
                f"Milestone announcement sent for {category}: {milestone_count} players"
            )
        except Exception:
            logger.exception(
                f"Failed to send milestone announcement for {category}: {milestone_count}"
            )

    @tasks.loop(minutes=15.0)
    async def poll_task(self):
        await self.bot.wait_until_ready()
        resp = await self._rcon_list()

        # Even if RCON fails (resp is None), we might want to update the embed
        # to show old data, but let's only proceed if we get a response to verify online status.
        if resp is None:
            logger.warning("RCON connection failed or returned empty.")
            return

        current_online_names = self._parse_list_response(resp)

        if not isinstance(self.storage, dict):
            self.storage = {"message_id": 0, "players": {}}

        players = self.storage.setdefault("players", {})
        now_ts = datetime.now(timezone.utc).timestamp()

        # Update timestamps for currently online players
        for n in current_online_names:
            players[n] = now_ts

        # Cleanup: Remove entries older than 5 years
        cutoff = now_ts - (5 * 365 * 24 * 3600)
        self.storage["players"] = {
            n: ts for n, ts in players.items() if float(ts) >= cutoff
        }


        # Get player counts for all categories
        last24, last72, last7d, last14d, all_time = self._categorize_players()
        all_time_count = len(all_time)
        last24_count = len(last24)
        last72_count = len(last72)
        last7d_count = len(last7d)
        last14d_count = len(last14d)

        # Check for all-time milestone achievements
        announced_milestones = self.storage.setdefault("announced_milestones", [])
        milestone = self._get_next_milestone(all_time_count)
        if milestone and milestone not in announced_milestones:
            await self._send_milestone_announcement(milestone, category="all_time")
            announced_milestones.append(milestone)
            self.storage["announced_milestones"] = announced_milestones

        # Check for last 24 hours milestone achievements
        announced_last24 = self.storage.setdefault("announced_last24_milestones", [])
        milestone_24 = self._get_next_10_milestone(last24_count)
        if milestone_24 and milestone_24 not in announced_last24:
            await self._send_milestone_announcement(milestone_24, category="last24")
            announced_last24.append(milestone_24)
            self.storage["announced_last24_milestones"] = announced_last24

        # Check for last 72 hours milestone achievements
        announced_last72 = self.storage.setdefault("announced_last72_milestones", [])
        milestone_72 = self._get_next_10_milestone(last72_count)
        if milestone_72 and milestone_72 not in announced_last72:
            await self._send_milestone_announcement(milestone_72, category="last72")
            announced_last72.append(milestone_72)
            self.storage["announced_last72_milestones"] = announced_last72

        # Check for last 7 days milestone achievements
        announced_last7d = self.storage.setdefault("announced_last7d_milestones", [])
        milestone_7d = self._get_next_10_milestone(last7d_count)
        if milestone_7d and milestone_7d not in announced_last7d:
            await self._send_milestone_announcement(milestone_7d, category="last7d")
            announced_last7d.append(milestone_7d)
            self.storage["announced_last7d_milestones"] = announced_last7d

        # Check for last 14 days milestone achievements
        announced_last14d = self.storage.setdefault("announced_last14d_milestones", [])
        milestone_14d = self._get_next_10_milestone(last14d_count)
        if milestone_14d and milestone_14d not in announced_last14d:
            await self._send_milestone_announcement(milestone_14d, category="last14d")
            announced_last14d.append(milestone_14d)
            self.storage["announced_last14d_milestones"] = announced_last14d

        embed = self._build_embed()
        channel = self.bot.get_channel(STATS_CHANNEL_ID)

        if not channel:
            return

        msg_id = int(self.storage.get("message_id", 0) or 0)

        # Helper to send fresh
        async def send_fresh():
            msg = await channel.send(embed=embed)
            self.storage["message_id"] = msg.id
            self._save_storage()

        try:
            if msg_id:
                try:
                    msg = await channel.fetch_message(msg_id)
                    await msg.edit(embed=embed)
                    self._save_storage()
                except discord.NotFound:
                    await send_fresh()
            else:
                await send_fresh()
        except Exception:
            logger.exception("Error updating stats message")

    @poll_task.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(PlayersOnline(bot))
