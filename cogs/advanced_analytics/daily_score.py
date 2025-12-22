import discord
from discord.ext import commands, tasks
from datetime import time, timezone
import analytics_core

# CONFIG: Where to send the daily report
REPORT_CHANNEL_ID = 1452598796377653331


class DailyScore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_report_task.start()

    def calculate_score(self, data):
        discord_stats = data["discord"]
        mc_stats = data["minecraft"]

        # --- HARD MODE FORMULA (Target: 20-25 is Good) ---

        # 1. Messages (Target: 500 msgs = 25 pts)
        msg_pts = (discord_stats["total_messages"] / 500) * 25

        # 2. Unique Chatters (Target: 15 people = 25 pts)
        chatters_count = len(discord_stats["unique_chatters"])
        chatter_pts = (chatters_count / 15) * 25

        # 3. MC Peak Players (Target: 8 players = 30 pts)
        mc_pts = (mc_stats["peak_players"] / 8) * 30

        # 4. Growth (Target: 2 joins = 20 pts)
        growth_pts = (discord_stats["joins"] / 2) * 20

        total = msg_pts + chatter_pts + mc_pts + growth_pts
        return min(round(total, 1), 100)  # Cap at 100

    @tasks.loop(time=time(hour=0, minute=0, tzinfo=timezone.utc))  # Midnight UTC
    async def daily_report_task(self):
        # We want YESTERDAY'S data because it just turned midnight
        # But for simplicity, let's load the data and find the most recent complete entry
        # Or just use "ensure_today" and if it's 00:00, use the day object that was just filled.

        data = analytics_core.load_data()
        today_str = analytics_core.get_today_str()

        if today_str not in data:
            return  # No data to report

        day_data = data[today_str]
        score = self.calculate_score(day_data)

        # Determine Color & Status
        if score >= 80:
            color = discord.Color.gold()
            status = "🏆 LEGENDARY"
        elif score >= 50:
            color = discord.Color.purple()
            status = "🔥 ON FIRE"
        elif score >= 20:
            color = discord.Color.green()
            status = "✅ GOOD"
        else:
            color = discord.Color.red()
            status = "💤 SLOW"

        embed = discord.Embed(
            title=f"📅 Daily Server Pulse: {today_str}",
            description=f"## Score: {score}/100\n**Status:** {status}",
            color=color,
        )

        # Discord Field
        d = day_data["discord"]
        top_talkers = sorted(
            d["unique_chatters"].items(), key=lambda x: x[1], reverse=True
        )[:3]
        top_talkers_str = (
            "\n".join([f"<@{u}>: {c}" for u, c in top_talkers])
            if top_talkers
            else "None"
        )

        embed.add_field(
            name="💬 Discord Stats",
            value=f"""
        **Msgs:** {d["total_messages"]}
        **Chatters:** {len(d["unique_chatters"])}
        **Joins:** {d["joins"]}
        **Top Talkers:**\n{top_talkers_str}
        """,
            inline=True,
        )

        # Minecraft Field
        m = day_data["minecraft"]
        avg_playtime = 0
        if len(m["unique_logins"]) > 0:
            avg_playtime = (m["total_playtime_checks"] * 15) / len(m["unique_logins"])

        embed.add_field(
            name="⛏️ Minecraft Stats",
            value=f"""
        **Peak Players:** {m["peak_players"]}
        **Unique Logins:** {len(m["unique_logins"])}
        **Avg Playtime:** {int(avg_playtime)} mins
        """,
            inline=True,
        )

        channel = self.bot.get_channel(REPORT_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)

    @daily_report_task.before_loop
    async def before_report(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(DailyScore(bot))
