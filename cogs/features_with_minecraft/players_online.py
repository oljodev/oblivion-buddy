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

STATS_CHANNEL_ID = 1433549179942338570

logger = logging.getLogger(__name__)

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
                json.dump({"message_id": 0, "players": {}}, f)

    def _load_storage(self):
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self.storage = json.load(f)
        except Exception:
            self.storage = {"message_id": 0, "players": {}}

        self.storage.setdefault("message_id", 0)
        self.storage.setdefault("players", {})

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
        all_time = []

        for name, ts in players.items():
            all_time.append(name)
            try:
                age_hours = (now - float(ts)) / 3600.0
                if age_hours <= 24:
                    last24.append(name)
                if age_hours <= 72:
                    last72.append(name)
            except ValueError:
                continue

        def sort_nocase(lst):
            return sorted(lst, key=lambda s: s.lower())

        return sort_nocase(last24), sort_nocase(last72), sort_nocase(all_time)

    def _build_embed(self):
        now = datetime.now(timezone.utc)
        embed = discord.Embed(
            title="Players Online",
            description="Recent activity on the server.",
            colour=discord.Colour.green(),
            timestamp=now,
        )
        last24, last72, all_time = self._categorize_players()

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
        # Using inline=False generally looks better for wide lists of names

        # Optional: Only show all time count, or a truncated list if huge
        embed.add_field(
            name=f"All Time Unique ({len(all_time)})", value=fmt(all_time), inline=False
        )

        embed.set_footer(text="Auto-updates every 5 minutes")
        return embed

    @tasks.loop(minutes=5.0)
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
