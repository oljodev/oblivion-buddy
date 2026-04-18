import discord
from discord.ext import commands, tasks
from datetime import date, time, timedelta, timezone
from cogs.advanced_analytics import analytics_core
from config import Channel

REPORT_CHANNEL_ID = Channel.LOG


class DailyScore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_report_task.start()
        self.weekly_report_task.start()

    def calculate_score(self, data):
        d = data["discord"]
        m = data["minecraft"]

        # Each component is individually capped before summing
        msg_pts = min((d["total_messages"] / 50) * 20, 20)
        chatter_pts = min((len(d["unique_chatters"]) / 10) * 20, 20)
        voice_pts = min((d["voice_minutes"] / 120) * 15, 15)
        mc_peak_pts = min((m["peak_players"] / 6) * 25, 25)
        mc_login_pts = min((len(m["unique_logins"]) / 5) * 10, 10)
        join_pts = min((d["joins"] / 2) * 10, 10)

        total = msg_pts + chatter_pts + voice_pts + mc_peak_pts + mc_login_pts + join_pts
        return round(min(total, 100), 1)

    def score_status(self, score):
        if score >= 80:
            return discord.Color.gold(), "🏆 LEGENDARY"
        elif score >= 60:
            return discord.Color.purple(), "🔥 ON FIRE"
        elif score >= 35:
            return discord.Color.green(), "✅ GOOD"
        else:
            return discord.Color.red(), "💤 SLOW"

    def build_daily_embed(self, date_str, day_data, score):
        color, status = self.score_status(score)
        embed = discord.Embed(
            title=f"📅 Daily Server Pulse: {date_str}",
            description=f"## Score: {score}/100\n**Status:** {status}",
            color=color,
        )

        d = day_data["discord"]
        top_talkers = sorted(d["unique_chatters"].items(), key=lambda x: x[1], reverse=True)[:3]
        top_talkers_str = (
            "\n".join([f"<@{u}>: {c}" for u, c in top_talkers]) if top_talkers else "None"
        )
        embed.add_field(
            name="💬 Discord Stats",
            value=(
                f"**Msgs:** {d['total_messages']}\n"
                f"**Chatters:** {len(d['unique_chatters'])}\n"
                f"**Voice:** {d['voice_minutes']} min\n"
                f"**Joins:** {d['joins']}\n"
                f"**Top Talkers:**\n{top_talkers_str}"
            ),
            inline=True,
        )

        m = day_data["minecraft"]
        avg_playtime = 0
        if len(m["unique_logins"]) > 0:
            avg_playtime = (m["total_playtime_checks"] * 15) / len(m["unique_logins"])
        embed.add_field(
            name="⛏️ Minecraft Stats",
            value=(
                f"**Peak Players:** {m['peak_players']}\n"
                f"**Unique Logins:** {len(m['unique_logins'])}\n"
                f"**Avg Playtime:** {int(avg_playtime)} min"
            ),
            inline=True,
        )

        score_breakdown = (
            f"Messages: {min(round((d['total_messages']/50)*20,1),20)}/20\n"
            f"Chatters: {min(round((len(d['unique_chatters'])/10)*20,1),20)}/20\n"
            f"Voice: {min(round((d['voice_minutes']/120)*15,1),15)}/15\n"
            f"MC Peak: {min(round((m['peak_players']/6)*25,1),25)}/25\n"
            f"MC Logins: {min(round((len(m['unique_logins'])/5)*10,1),10)}/10\n"
            f"Joins: {min(round((d['joins']/2)*10,1),10)}/10"
        )
        embed.add_field(name="📊 Score Breakdown", value=score_breakdown, inline=False)

        return embed

    @tasks.loop(time=time(hour=21, minute=59, tzinfo=timezone.utc))  # 23:59 GMT+2
    async def daily_report_task(self):
        # Report TODAY — the day is ending at 23:59 local time
        yesterday = date.today().strftime("%Y-%m-%d")
        data = analytics_core.load_data()

        if yesterday not in data:
            return

        day_data = data[yesterday]
        score = self.calculate_score(day_data)
        embed = self.build_daily_embed(yesterday, day_data, score)

        channel = self.bot.get_channel(REPORT_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)

    @tasks.loop(time=time(hour=21, minute=59, tzinfo=timezone.utc))  # 23:59 GMT+2
    async def weekly_report_task(self):
        # Only run on Sunday (weekday 6)
        if date.today().weekday() != 6:
            return

        data = analytics_core.load_data()
        today = date.today()
        week_days = []

        for i in range(0, 7):  # today + last 6 days
            d = today - timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            if d_str in data:
                s = self.calculate_score(data[d_str])
                week_days.append((d_str, s))

        if not week_days:
            return

        scores = [s for _, s in week_days]
        avg_score = round(sum(scores) / len(scores), 1)
        best_day = max(week_days, key=lambda x: x[1])
        worst_day = min(week_days, key=lambda x: x[1])

        color, status = self.score_status(avg_score)
        week_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
        week_end = today.strftime("%Y-%m-%d")

        embed = discord.Embed(
            title=f"📊 Weekly Server Pulse: {week_start} → {week_end}",
            description=f"## Avg Score: {avg_score}/100\n**Status:** {status}",
            color=color,
        )

        scores_str = "\n".join([f"{d}: **{s}**" for d, s in sorted(week_days)])
        embed.add_field(name="📅 Daily Scores", value=scores_str, inline=False)
        embed.add_field(name="🥇 Best Day", value=f"{best_day[0]}: **{best_day[1]}**", inline=True)
        embed.add_field(name="📉 Worst Day", value=f"{worst_day[0]}: **{worst_day[1]}**", inline=True)
        embed.add_field(name="📈 Days Tracked", value=str(len(scores)), inline=True)

        channel = self.bot.get_channel(REPORT_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)

    @daily_report_task.before_loop
    @weekly_report_task.before_loop
    async def before_report(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(DailyScore(bot))
