import discord
from datetime import datetime, timezone, timedelta
from discord.ext import commands, tasks
from discord.ui import View, Button
from cogs.advanced_analytics import analytics_core
from config import Channel
DISCORD_STATS_CHANNEL_ID = Channel.ADVANCED_STATS
MINECRAFT_STATS_CHANNEL_ID = Channel.ADVANCED_STATS

GMT2 = timezone(timedelta(hours=2))


def get_sorted_dates():
    data = analytics_core.load_data()
    dates = [k for k in data.keys() if k != "meta" and k[0].isdigit()]
    dates.sort()
    return dates


class HistoryView(View):
    def __init__(self, mode, current_date_index):
        super().__init__(timeout=None)  # Make buttons permanent
        self.mode = mode
        self.index = current_date_index
        self.dates = get_sorted_dates()
        self.update_buttons()

    def update_buttons(self):
        # Disable buttons when at the start/end of history
        self.children[0].disabled = self.index == 0
        self.children[1].disabled = self.index == len(self.dates) - 1

    def get_embed(self):
        self.dates = get_sorted_dates()
        date_str = self.dates[self.index]
        data = analytics_core.load_data()[date_str]

        if self.mode == "discord":
            d = data["discord"]
            # Topp 10 Liste
            sorted_chatters = sorted(
                d["unique_chatters"].items(), key=lambda x: x[1], reverse=True
            )[:10]
            top_list = "\n".join(
                [
                    f"{i + 1}. <@{uid}> - **{c}**"
                    for i, (uid, c) in enumerate(sorted_chatters)
                ]
            )

            embed = discord.Embed(
                title=f"📊 Discord Statistics: {date_str}",
                color=discord.Color.blurple(),
                timestamp=datetime.now(),
            )
            embed.add_field(
                name="Messages", value=str(d["total_messages"]), inline=True
            )
            embed.add_field(
                name="Active in chat", value=str(len(d["unique_chatters"])), inline=True
            )
            embed.add_field(name="New members", value=str(d["joins"]), inline=True)
            embed.add_field(
                name="🏆 Top 10 Chatters",
                value=top_list if top_list else "No data",
                inline=False,
            )
            embed.set_footer(text=f"Page {self.index + 1} of {len(self.dates)}")
            return embed

        elif self.mode == "minecraft":
            m = data["minecraft"]
            avg_mins = 0
            if len(m["unique_logins"]) > 0:
                avg_mins = (m["total_playtime_checks"] * 15) / len(m["unique_logins"])

            # Activity % for this day (GMT+2)
            active_slots = m.get("active_slots", 0)
            today_gmt2 = datetime.now(GMT2).strftime("%Y-%m-%d")
            if date_str == today_gmt2:
                now_gmt2 = datetime.now(GMT2)
                elapsed_minutes = now_gmt2.hour * 60 + now_gmt2.minute
            else:
                elapsed_minutes = 1440
            if elapsed_minutes > 0:
                activity_pct = min((active_slots * 15 / elapsed_minutes) * 100, 100)
            else:
                activity_pct = 0.0

            embed = discord.Embed(
                title=f"⛏️ Minecraft Statistics: {date_str}",
                color=discord.Color.green(),
                timestamp=datetime.now(),
            )
            embed.add_field(
                name="Peak Players", value=str(m["peak_players"]), inline=True
            )
            embed.add_field(
                name="Unique Logins", value=str(len(m["unique_logins"])), inline=True
            )
            embed.add_field(
                name="Avg Playtime", value=f"{int(avg_mins)} min", inline=True
            )
            embed.add_field(
                name="Server Activity",
                value=f"{activity_pct:.1f}% of the day had players online",
                inline=False,
            )

            p_list = ", ".join(m["unique_logins"])
            embed.add_field(
                name="Players online",
                value=p_list if p_list else "None",
                inline=False,
            )
            embed.set_footer(text=f"Page {self.index + 1} of {len(self.dates)}")
            return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.gray)
    async def prev(self, interaction: discord.Interaction, button: Button):
        if self.index > 0:
            self.index -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: Button):
        self.dates = get_sorted_dates()
        if self.index < len(self.dates) - 1:
            self.index += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)


class InteractiveStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_update.start()

    @tasks.loop(minutes=15)
    async def auto_update(self):
        """Updates the embed every 15 minutes to show live data for today"""
        await self.bot.wait_until_ready()

        data = analytics_core.load_data()
        if "meta" not in data:
            data["meta"] = {}

        dates = get_sorted_dates()
        if not dates:
            return

        latest_idx = len(dates) - 1

        # Update Discord message
        await self.sync_message("discord", DISCORD_STATS_CHANNEL_ID, latest_idx)
        # Update Minecraft message
        await self.sync_message("minecraft", MINECRAFT_STATS_CHANNEL_ID, latest_idx)

    async def sync_message(self, mode, channel_id, latest_idx):
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        data = analytics_core.load_data()
        msg_key = f"{mode}_msg_id"
        msg_id = data.get("meta", {}).get(msg_key)

        view = HistoryView(mode, latest_idx)
        embed = view.get_embed()

        if msg_id:
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed, view=view)
            except discord.NotFound:
                new_msg = await channel.send(embed=embed, view=view)
                data["meta"][msg_key] = new_msg.id
                analytics_core.save_data(data)
        else:
            new_msg = await channel.send(embed=embed, view=view)
            if "meta" not in data:
                data["meta"] = {}
            data["meta"][msg_key] = new_msg.id
            analytics_core.save_data(data)

    @auto_update.before_loop
    async def before_auto_update(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(InteractiveStats(bot))
