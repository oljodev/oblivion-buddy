from discord.ext import commands, tasks
from datetime import datetime
import re
from aiomcrcon import Client
from cogs.advanced_analytics import analytics_core

# RCON Config
from config import RCON_IP, RCON_PORT, RCON_PASS as RCON_PASSWORD

MC_NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")

BLACKLIST_NAMES = {
    "there", "are", "of", "max", "players", "online", "server", "info",
    "list", "connected", "joined", "left", "for", "get", "set", "value",
    "playtime", "none", "null", "the", "and", "from", "with", "have",
    "has", "was", "not", "out", "all", "any", "can", "cant", "true",
    "false", "error", "warn", "warning", "debug", "trigger", "scoreboard",
    "objective", "objectives", "score", "found", "unknown", "missing",
}


def _parse_player_list(response) -> list[str]:
    """Parse RCON 'list' response into valid player names.

    Returns [] if the response doesn't match the expected "...online: ..."
    shape — better to miss one poll than to permanently poison analytics
    with words from an error message.
    """
    if isinstance(response, (tuple, list)):
        text = str(response[0])
    else:
        text = str(response) if response else ""

    match = re.search(r"online:?\s*(.*)", text, re.IGNORECASE)
    if not match:
        return []
    raw = match.group(1)

    players = []
    for token in re.split(r"[,\s]+", raw):
        name = re.sub(r"^[^A-Za-z0-9_]+|[^A-Za-z0-9_]+$", "", token)
        if not MC_NAME_RE.match(name):
            continue
        if name.lower() in BLACKLIST_NAMES:
            continue
        if name.isdigit():
            continue
        players.append(name)

    seen = set()
    unique = []
    for n in players:
        if n.lower() not in seen:
            seen.add(n.lower())
            unique.append(n)
    return unique


class DataCollector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_sessions = {}  # {user_id: start_datetime}
        self.mc_poll_task.start()

    # --- Discord Events ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        data = analytics_core.ensure_today_exists()
        today = analytics_core.get_today_str()

        # 1. Total Messages
        data[today]["discord"]["total_messages"] += 1

        # 2. Unique Chatters
        uid = str(message.author.id)
        current_count = data[today]["discord"]["unique_chatters"].get(uid, 0)
        data[today]["discord"]["unique_chatters"][uid] = current_count + 1

        analytics_core.save_data(data)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        data = analytics_core.ensure_today_exists()
        today = analytics_core.get_today_str()
        data[today]["discord"]["joins"] += 1
        analytics_core.save_data(data)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # User Joined Voice
        if not before.channel and after.channel:
            self.voice_sessions[member.id] = datetime.now()

        # User Left Voice
        elif before.channel and not after.channel:
            if member.id in self.voice_sessions:
                start_time = self.voice_sessions.pop(member.id)
                duration = (datetime.now() - start_time).total_seconds() / 60

                data = analytics_core.ensure_today_exists()
                today = analytics_core.get_today_str()
                data[today]["discord"]["voice_minutes"] += int(duration)
                analytics_core.save_data(data)

    # --- Minecraft RCON Loop (Every 15 mins) ---
    @tasks.loop(minutes=15)
    async def mc_poll_task(self):
        try:
            async with Client(RCON_IP, RCON_PORT, RCON_PASSWORD) as client:
                response = await client.send_cmd("list")

                players = _parse_player_list(response)

                data = analytics_core.ensure_today_exists()
                today = analytics_core.get_today_str()
                mc_data = data[today]["minecraft"]

                # 1. Update Peak
                current_count = len(players)
                if current_count > mc_data["peak_players"]:
                    mc_data["peak_players"] = current_count

                # 2. Unique Logins & Playtime
                for p in players:
                    if p not in mc_data["unique_logins"]:
                        mc_data["unique_logins"].append(p)
                    mc_data["total_playtime_checks"] += 1

                # 3. Active slots (at least 1 player was online this poll)
                if players:
                    mc_data.setdefault("active_slots", 0)
                    mc_data["active_slots"] += 1

                analytics_core.save_data(data)

        except Exception as e:
            print(f"RCON Poll Error: {e}")

    @mc_poll_task.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(DataCollector(bot))
