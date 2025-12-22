from discord.ext import commands, tasks
from datetime import datetime
import os
import re
from aiomcrcon import Client
from cogs.advanced_analytics import analytics_core

# RCON Config
RCON_IP = os.getenv("RCON_IP", "localhost")
RCON_PORT = int(os.getenv("RCON_PORT", 25575))
RCON_PASSWORD = os.getenv("RCON_PASS", "secret")


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

                # Parse players (Simple regex for "online: name, name")
                # Adjust regex if your server output is different
                match = re.search(r"online:?\s*(.*)", response, re.IGNORECASE)
                players = []
                if match and match.group(1):
                    raw = match.group(1).replace(",", " ")
                    players = [p.strip() for p in raw.split() if p.strip()]

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
                    # Add 15 mins of "playtime points" (1 check = 15 mins)
                    mc_data["total_playtime_checks"] += 1

                analytics_core.save_data(data)

        except Exception as e:
            print(f"RCON Poll Error: {e}")

    @mc_poll_task.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(DataCollector(bot))
