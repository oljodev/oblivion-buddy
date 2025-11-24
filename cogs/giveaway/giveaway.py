import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import logging
import random
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Giveaway")
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

GUILD_ID = discord.Object(id=1422932147550818507)

OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090
MEMBER_ROLE_ID = 1422937958897422406

# New: persistence file path and helpers
GIVEAWAYS_FILE = Path(__file__).parent / "giveaways.json"


def _atomic_write(path: Path, data: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_saved_giveaways():
    try:
        if not GIVEAWAYS_FILE.exists():
            return {}
        with GIVEAWAYS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load giveaways.json: {e}")
        return {}


def save_all_giveaways(data: dict):
    try:
        GIVEAWAYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(GIVEAWAYS_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save giveaways.json: {e}")


def add_saved_giveaway(
    message_id: int,
    channel_id: int,
    guild_id: int,
    end_ts: int,
    host_id: int,
    prize: str,
    winners: int,
    description: str,
    entries: list,
    places: int,
):
    data = load_saved_giveaways()
    data[str(message_id)] = {
        "message_id": message_id,
        "channel_id": channel_id,
        "guild_id": guild_id,
        "end_ts": end_ts,
        "host_id": host_id,
        "prize": prize,
        "winners": winners,
        "description": description,
        "entries": entries,
        "places": places,
    }
    save_all_giveaways(data)


def update_saved_entries(message_id: int, entries: list):
    data = load_saved_giveaways()
    key = str(message_id)
    if key in data:
        data[key]["entries"] = entries
        save_all_giveaways(data)


def remove_saved_giveaway(message_id: int):
    data = load_saved_giveaways()
    key = str(message_id)
    if key in data:
        data.pop(key)
        save_all_giveaways(data)


class JoinGiveawayButton(discord.ui.View):
    def __init__(self, end_time, host, prize, winners, description, places=1):
        super().__init__(timeout=None)
        self.entries = []
        self.end_time = end_time
        self.host = host
        self.prize = prize
        self.description = description
        # winners represents how many top-winners get the main prize;
        # but if places > 1 we force winners to 1 (as required)
        self.places = max(1, min(3, int(places or 1)))
        if self.places > 1:
            self.winners = 1
        else:
            self.winners = int(winners)
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
            # Persist updated entries
            try:
                if hasattr(self, "message") and self.message:
                    update_saved_entries(self.message.id, self.entries)
            except Exception as e:
                logger.error(f"Failed to update saved entries: {e}")
            await interaction.response.send_message(
                "You joined the giveaway! 🎉 Wait 1 Minute and the Enteries number will change!",
                ephemeral=True,
            )

    @tasks.loop(seconds=1)
    async def update_countdown(self):
        # Update embed every second
        now = datetime.utcnow()
        remaining = self.end_time - now

        if remaining.total_seconds() > 600:
            try:
                self.update_countdown.change_interval(seconds=60)

            except Exception:
                pass
            try:
                embed = self.message.embeds[0]
                embed.set_field_at(
                    0,
                    name="Ends",
                    value=f"in {str(remaining).split('.')[0]}",
                    inline=False,
                )
                embed.set_field_at(
                    2, name="Entries", value=str(len(self.entries)), inline=True
                )
                await self.message.edit(embed=embed, view=self)
            except Exception as e:
                logger.error(f"⚠️ Failed to update countdown (minute interval): {e}")
            return

        else:
            try:
                self.update_countdown.change_interval(seconds=1)
            except Exception:
                pass

        if remaining.total_seconds() <= 0:
            self.update_task.cancel()
            self.ended = True
            self.disable_all_buttons()

            # 🎯 Choose winner(s) depending on places
            result_text = ""
            if self.entries:
                if self.places <= 1:
                    # behave like before: possibly multiple winners for the top prize
                    top_count = min(self.winners, len(self.entries))
                    winners = random.sample(self.entries, top_count)
                    if top_count == 1:
                        winner_mentions = ", ".join(f"<@{uid}>" for uid in winners)
                        result_text = f"🎉 Congratulations {winner_mentions}! You won **{self.prize}**!"
                    else:
                        winner_mentions = ", ".join(f"<@{uid}>" for uid in winners)
                        result_text = f"🎉 Congratulations {winner_mentions}! You each won **{self.prize}**!"
                else:
                    # Multiple places: First, Second, Third (max 3), distinct winners
                    place_names = ["First", "Second", "Third"]
                    count = min(self.places, len(self.entries))
                    chosen = random.sample(self.entries, count)
                    lines = []
                    for idx, uid in enumerate(chosen):
                        if idx == 0:
                            # First place — full prize
                            lines.append(
                                f"🥇 {place_names[idx]} place — <@{uid}> — won **{self.prize}**"
                            )
                        elif idx == 1:
                            # Second place — runner-up
                            lines.append(
                                f"🥈 {place_names[idx]} place — <@{uid}> — won a runner-up prize."
                            )
                        else:
                            # Third place — consolation
                            lines.append(
                                f"🥉 {place_names[idx]} place — <@{uid}> — won a consolation prize."
                            )
                    result_text = "🎉 Giveaway results:\n" + "\n".join(lines)
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
            # show places info in embed for clarity
            ended_embed.add_field(
                name="Winners",
                value=str(self.winners)
                + (f" (places: {self.places})" if self.places > 1 else ""),
                inline=True,
            )
            ended_embed.set_footer(text="Giveaway Ended")

            if hasattr(self, "message"):
                try:
                    await self.message.edit(embed=ended_embed, view=self)
                except Exception as e:
                    logger.error(f"⚠️ Failed to edit message: {e}")
                finally:
                    await self.message.channel.send(result_text)
            # Remove from persisted storage
            try:
                if hasattr(self, "message") and self.message:
                    remove_saved_giveaway(self.message.id)
            except Exception as e:
                logger.error(f"Failed to remove saved giveaway: {e}")
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
                embed.set_field_at(
                    0,
                    name="Ends",
                    value=f"in {str(remaining).split('.')[0]}",
                    inline=False,
                )
                embed.set_field_at(
                    1, name="Hosted by", value=self.host.mention, inline=True
                )
                embed.set_field_at(
                    2, name="Entries", value=str(len(self.entries)), inline=True
                )
                embed.set_field_at(
                    3, name="Winners", value=str(self.winners), inline=True
                )
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
            try:
                embed = self.message.embeds[0]
                embed.set_field_at(
                    0,
                    name="Ends",
                    value=f"in {str(remaining).split('.')[0]}",
                    inline=False,
                )
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
        self.places = discord.ui.TextInput(
            label="First, Second, Third Places",
            placeholder="Choose between first (1), second (2), third (3) places. ",
            required=True,
        )

        for field in [
            self.prize,
            self.duration,
            self.winner_count,
            self.description,
            self.places,
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

        # parse winner count input
        try:
            winner_count_val = int(self.winner_count.value.strip())
            if winner_count_val < 1:
                winner_count_val = 1
        except Exception:
            await interaction.response.send_message(
                "Invalid number of winners! Provide a positive integer.", ephemeral=True
            )
            return

        # parse places (1-3)
        try:
            places_val = int(self.places.value.strip())
            if places_val < 1:
                places_val = 1
            if places_val > 3:
                places_val = 3
        except Exception:
            await interaction.response.send_message(
                "Invalid places value! Enter 1, 2 or 3.", ephemeral=True
            )
            return

        # If user requested multiple places, enforce top-winner count to 1
        if places_val > 1:
            winner_count_val = 1

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
        embed.add_field(name="Winners", value=str(winner_count_val), inline=True)
        embed.set_footer(text=f"Today at {datetime.utcnow().strftime('%H:%M UTC')}")

        view = JoinGiveawayButton(
            end_time,
            interaction.user,
            self.prize.value,
            int(winner_count_val),
            self.description.value,
            places=places_val,
        )
        msg = await interaction.channel.send(embed=embed, view=view)
        view.message = msg

        # Persist the newly created giveaway
        try:
            add_saved_giveaway(
                message_id=msg.id,
                channel_id=msg.channel.id,
                guild_id=msg.guild.id,
                end_ts=int(end_time.timestamp()),
                host_id=interaction.user.id,
                prize=self.prize.value,
                winners=int(winner_count_val),
                description=self.description.value or "",
                entries=[],
                places=places_val,
            )
        except Exception as e:
            logger.error(f"Failed to persist giveaway: {e}")

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
        self._restored = False

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

    # New: restore persisted giveaways on ready
    @commands.Cog.listener()
    async def on_ready(self):
        if self._restored:
            return
        self._restored = True

        data = load_saved_giveaways()
        if not data:
            return

        for key, info in data.items():
            try:
                channel_id = info["channel_id"]
                message_id = info["message_id"]
                end_ts = info["end_ts"]
                host_id = info["host_id"]
                prize = info["prize"]
                winners = info.get("winners", 1)
                description = info.get("description", "")
                entries = info.get("entries", [])
                places = int(info.get("places", 1))

                # If restored giveaway had multiple places, ensure winners is 1
                if places > 1:
                    winners = 1

                try:
                    channel = self.bot.get_channel(
                        channel_id
                    ) or await self.bot.fetch_channel(channel_id)
                except Exception:
                    logger.error(
                        f"Failed to fetch channel {channel_id} for saved giveaway {message_id}"
                    )
                    continue

                try:
                    message = await channel.fetch_message(message_id)
                except Exception:
                    logger.error(
                        f"Failed to fetch message {message_id} in channel {channel_id}; removing saved giveaway"
                    )
                    remove_saved_giveaway(message_id)
                    continue

                host = None
                try:
                    host = await self.bot.fetch_user(host_id)
                except Exception:
                    # fallback to a dummy user-like object
                    host = message.guild.get_member(host_id) or message.author

                end_time = datetime.utcfromtimestamp(end_ts)
                view = JoinGiveawayButton(
                    end_time, host, prize, winners, description, places=places
                )
                view.entries = entries
                view.message = message

                # Register persistent view so interactions continue to work
                try:
                    self.bot.add_view(view, message.id)
                except Exception:
                    # older discord.py versions might not accept message_id argument; editing message with view also attaches it
                    try:
                        await message.edit(view=view)
                    except Exception:
                        logger.error(f"Failed to attach view to message {message_id}")

                self.active_giveaways[str(message.id)] = view
                logger.info(f"Restored giveaway {message.id} (ends {end_time})")
            except Exception as e:
                logger.error(f"Error while restoring giveaway {key}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
