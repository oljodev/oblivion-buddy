import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import logging
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Giveaway")
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

GUILD_ID = discord.Object(id=1422932147550818507)

OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090
MEMBER_ROLE_ID = 1422937958897422406


class JoinGiveawayButton(discord.ui.View):
    def __init__(self, end_time, host, prize, winners, description):
        super().__init__(timeout=None)
        self.entries = []
        self.end_time = end_time
        self.host = host
        self.prize = prize
        self.description = description
        self.winners = winners
        self.update_task = self.update_countdown.start()

    def disable_all_buttons(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="🎉", style=discord.ButtonStyle.blurple)
    async def join_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id in self.entries:
            await interaction.response.send_message(
                "You have already joined the giveaway!", ephemeral=True
            )
        else:
            self.entries.append(interaction.user.id)
            await interaction.response.send_message(
                "You joined the giveaway! 🎉", ephemeral=True
            )

    @tasks.loop(seconds=1)
    async def update_countdown(self):
        # Update embed every second
        now = datetime.utcnow()
        remaining = self.end_time - now

        # keep the existing optimization to avoid editing too often for long giveaways
        if remaining.total_seconds() > 600 and now.second % 60 != 0:
            return

        if remaining.total_seconds() <= 0:
            self.update_task.cancel()
            self.ended = True
            self.disable_all_buttons()

            # 🎯 Choose winner
            if self.entries:
                winners = random.sample(
                    self.entries, min(self.winners, len(self.entries))
                )
                winner_mentions = ", ".join(f"<@{uid}>" for uid in winners)
                result_text = (
                    f"🎉 Congratulations {winner_mentions}! You won **{self.prize}**!"
                )
            else:
                result_text = "No one entered the giveaway 😢"

            # ⚙️ Updated embed (gray and ended)
            ended_embed = discord.Embed(
                title=f"**{self.prize}**",
                description="This giveaway has ended.",
                color=discord.Color.dark_gray(),
            )
            ended_embed.add_field(
                name="Ended",
                value=f"<t:{int(self.end_time.timestamp())}:f>",
                inline=False,
            )
            ended_embed.add_field(
                name="Hosted by", value=self.host.mention, inline=True
            )
            ended_embed.add_field(
                name="Entries", value=str(len(self.entries)), inline=True
            )
            ended_embed.add_field(name="Winners", value=str(self.winners), inline=True)
            ended_embed.set_footer(text="Giveaway Ended")

            if hasattr(self, "message"):
                try:
                    await self.message.edit(embed=ended_embed, view=self)
                except Exception as e:
                    logger.error(f"⚠️ Failed to edit message: {e}")
                finally:
                    await self.message.channel.send(result_text)
            return

        # Format remaining time exactly like polls: use timedelta string (H:MM:SS / D days, H:MM:SS)
        time_str = str(remaining).split(".")[0]

        # If we have an existing message and an embed, update its fields in-place (same approach as Polls)
        if hasattr(self, "message") and self.message and self.message.embeds:
            try:
                embed = self.message.embeds[0]
                # Update the Ends field (field index 0)
                embed.set_field_at(
                    0,
                    name="Ends",
                    value=f"in {time_str} (<t:{int(self.end_time.timestamp())}:f>)",
                    inline=False,
                )
                # Update other fields to reflect live values
                # Hosted by (index 1), Entries (index 2), Winners (index 3)
                # Guard against unexpected field layout by checking field count
                if len(embed.fields) >= 2:
                    embed.set_field_at(
                        1, name="Hosted by", value=self.host.mention, inline=True
                    )
                if len(embed.fields) >= 3:
                    embed.set_field_at(
                        2, name="Entries", value=str(len(self.entries)), inline=True
                    )
                if len(embed.fields) >= 4:
                    embed.set_field_at(
                        3, name="Winners", value=str(self.winners), inline=True
                    )

                await self.message.edit(embed=embed, view=self)
            except Exception as e:
                logger.error(f"⚠️ Failed to update countdown (in-place): {e}")
                # Fallback to building a fresh embed if in-place update fails
                embed = discord.Embed(
                    title=f"**{self.prize}**",
                    description=self.description,
                    color=discord.Color.green(),
                )
                embed.add_field(
                    name="Ends",
                    value=f"in {time_str} (<t:{int(self.end_time.timestamp())}:f>)",
                    inline=False,
                )
                embed.add_field(name="Hosted by", value=self.host.mention, inline=True)
                embed.add_field(
                    name="Entries", value=str(len(self.entries)), inline=True
                )
                embed.add_field(name="Winners", value=str(self.winners), inline=True)
                embed.set_footer(
                    text=f"Ends at {self.end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                )
                if hasattr(self, "message"):
                    await self.message.edit(embed=embed, view=self)
        else:
            # No message/embed yet: create a fresh embed (initial send fallback)
            embed = discord.Embed(
                title=f"**{self.prize}**",
                description=self.description,
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Ends",
                value=f"in {time_str} (<t:{int(self.end_time.timestamp())}:f>)",
                inline=False,
            )
            embed.add_field(name="Hosted by", value=self.host.mention, inline=True)
            embed.add_field(name="Entries", value=str(len(self.entries)), inline=True)
            embed.add_field(name="Winners", value=str(self.winners), inline=True)
            embed.set_footer(
                text=f"Ends at {self.end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
            if hasattr(self, "message"):
                await self.message.edit(embed=embed, view=self)

    async def on_timeout(self):
        self.disable_all_buttons()
        if hasattr(self, "message"):
            await self.message.edit(view=self)


class GiveawayModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Create a Giveaway")

        self.prize = discord.ui.TextInput(
            label="Prize",
            placeholder="What is the prize?",
            required=True,
            max_length=100,
        )
        self.duration = discord.ui.TextInput(
            label="Duration",
            placeholder="How long should the giveaway last? (e.g. 1d, 1h, 30m)",
            required=True,
            max_length=50,
        )
        self.winner_count = discord.ui.TextInput(
            label="Number of Winners",
            placeholder="How many winners? (e.g. 1, 2)",
            required=True,
        )
        self.description = discord.ui.TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            placeholder="Additional details about the giveaway.",
            required=False,
            max_length=500,
        )
        self.start_time = discord.ui.TextInput(
            label="Start Time",
            placeholder="When should the giveaway start? (e.g. now, 2025-12-31 15:00)",
            required=False,
        )

        for field in [
            self.prize,
            self.duration,
            self.winner_count,
            self.description,
            self.start_time,
        ]:
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        # Enkel parser for varighet (bare m og h)
        dur_text = self.duration.value.strip().lower()
        seconds = 0

        if "d" in dur_text:
            seconds += int(dur_text.replace("d", "")) * 86400
        elif "h" in dur_text:
            seconds += int(dur_text.replace("h", "")) * 3600
        elif "m" in dur_text:
            seconds += int(dur_text.replace("m", "")) * 60
        else:
            await interaction.response.send_message(
                "Invalid duration! Use e.g. `1d`, `1h` or `30m`.", ephemeral=True
            )
            return

        end_time = datetime.utcnow() + timedelta(seconds=seconds)

        embed = discord.Embed(
            title=f"**{self.prize.value}**",
            description=self.description.value or "No description provided.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Ends",
            value=f"in {dur_text} (<t:{int(end_time.timestamp())}:f>)",
            inline=False,
        )
        embed.add_field(name="Hosted by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Entries", value="0", inline=True)
        embed.add_field(name="Winners", value=self.winner_count.value, inline=True)
        embed.set_footer(text=f"Today at {datetime.utcnow().strftime('%H:%M UTC')}")

        view = JoinGiveawayButton(
            end_time,
            interaction.user,
            self.prize.value,
            int(self.winner_count.value),
            self.description.value,
        )
        msg = await interaction.channel.send(embed=embed, view=view)
        view.message = msg

        await interaction.response.send_message("Giveaway created! 🎉", ephemeral=True)
        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if role:
            await interaction.channel.send(
                f"{role.mention} 🎉 A new giveaway has started!"
            )


class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.active_giveaways = {}
        self.bot = bot

    @app_commands.command(name="giveaway", description="Create a giveaway.")
    @app_commands.guilds(GUILD_ID)
    async def giveaway_command(self, interaction: discord.Interaction):
        allowed_roles = [
            OWNER_ROLE_ID,
            ADMIN_ROLE_ID,
        ]

        if not any(role.id in allowed_roles for role in interaction.user.roles):
            await interaction.response.send_message(
                "🚫 You don't have permission to start giveaways.", ephemeral=True
            )
            return

        await interaction.response.send_modal(GiveawayModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
