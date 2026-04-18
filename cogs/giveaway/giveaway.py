import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
import logging
import random
import json
import asyncio
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Giveaway")

from channels import GUILD_ID as _GUILD_ID, LOG_CHANNEL as LOG_CHANNEL_ID
from roles import OWNER_ROLE_ID, ADMIN_ROLE_ID, MEMBER_ROLE_ID, GIVEAWAY_STAFF_ROLE_ID

GUILD_ID = discord.Object(id=_GUILD_ID)

# Persistence
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
    prizes: list,
    description: str,
    entries: list,
    required_role_id: int,
    image_url: str,
):
    data = load_saved_giveaways()
    data[str(message_id)] = {
        "message_id": message_id,
        "channel_id": channel_id,
        "guild_id": guild_id,
        "end_ts": end_ts,
        "host_id": host_id,
        "prizes": prizes,
        "description": description,
        "entries": entries,
        "required_role_id": required_role_id,
        "image_url": image_url,
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


def parse_duration(duration_str: str) -> int:
    """Parses duration string like '1d 2h 30m' into total seconds."""
    matches = re.findall(r"(\d+)([dhm])", duration_str.lower())
    if not matches:
        return 0

    total_seconds = 0
    for amount, unit in matches:
        if unit == "d":
            total_seconds += int(amount) * 86400
        elif unit == "h":
            total_seconds += int(amount) * 3600
        elif unit == "m":
            total_seconds += int(amount) * 60
    return total_seconds


class JoinGiveawayButton(discord.ui.View):
    def __init__(
        self,
        end_time,
        host,
        prizes: list,
        description: str,
        required_role_id: int = None,
        image_url: str = None,
    ):
        super().__init__(timeout=None)
        self.entries = []
        self.end_time = end_time
        self.host = host
        self.prizes = prizes
        self.description = description
        self.required_role_id = required_role_id
        self.image_url = image_url
        self.ended = False

    def start_tasks(self):
        """Starts the countdown manually."""
        self.finish_task = asyncio.create_task(self.wait_for_end())

    def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def wait_for_end(self):
        now = datetime.utcnow()
        delay = (self.end_time - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await self.end_giveaway()

    async def end_giveaway(self):
        if self.ended:
            return
        self.ended = True
        self.disable_all_buttons()

        result_text_lines = []
        dm_tasks = []

        # SIKKERHET: Bruker serveren fra meldingen, ikke fra hosten (som kan være et User-objekt)
        guild = self.message.guild

        if not self.entries:
            result_text = "No one entered the giveaway 😢"
        else:
            # We shuffle the entries to pick random winners
            participants = list(self.entries)
            random.shuffle(participants)

            emojis = ["🥇", "🥈", "🥉", "🏅"]

            result_text_lines.append("🎉 **Giveaway Ended! Here are the winners:**\n")

            for idx, prize_name in enumerate(self.prizes):
                emoji = emojis[idx] if idx < 3 else emojis[-1]

                if idx < len(participants):
                    winner_id = participants[idx]
                    winner = guild.get_member(winner_id)

                    result_text_lines.append(
                        f"{emoji} **{prize_name}**: <@{winner_id}>"
                    )

                    if winner:
                        dm_embed = discord.Embed(
                            title="🎉 You won a giveaway!",
                            description=f"Congratulations! You won **{prize_name}** in the giveaway hosted on **{guild.name}**!\n\nPlease create a ticket in {guild.name} to claim your prize.",
                            color=discord.Color.gold(),
                        )
                        dm_tasks.append(winner.send(embed=dm_embed))
                else:
                    result_text_lines.append(
                        f"{emoji} **{prize_name}**: *Not enough participants*"
                    )

            result_text = "\n".join(result_text_lines)

        # Send DM to host about winners
        try:
            winner_dm = discord.Embed(
                title="Giveaway Ended - Winners Selected",
                description=result_text,
                color=discord.Color.gold(),
                timestamp=datetime.utcnow(),
            )
            await self.host.send(embed=winner_dm)
        except discord.Forbidden:
            pass

        # Update embed to gray
        ended_embed = discord.Embed(
            title="Giveaway Ended",
            description=self.description or "This giveaway has ended.",
            color=discord.Color.dark_gray(),
        )
        if self.image_url:
            ended_embed.set_thumbnail(url=self.image_url)

        ended_embed.add_field(
            name="Ended", value=f"<t:{int(self.end_time.timestamp())}:f>", inline=False
        )
        ended_embed.add_field(name="Hosted by", value=self.host.mention, inline=True)
        ended_embed.add_field(
            name="Total Entries", value=str(len(self.entries)), inline=True
        )

        if hasattr(self, "message"):
            try:
                await self.message.edit(embed=ended_embed, view=self)
                await self.message.channel.send(result_text)
                remove_saved_giveaway(self.message.id)
            except Exception as e:
                logger.error(f"Error ending giveaway: {e}")

        # Send DMs in background
        for task in dm_tasks:
            try:
                await task
            except discord.Forbidden:
                pass  # Closed DMs

    @discord.ui.button(
        label="🎉 Join", style=discord.ButtonStyle.blurple, custom_id="join_giveaway"
    )
    async def join_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.ended:
            return await interaction.response.send_message(
                "This giveaway has already ended!", ephemeral=True
            )

        # Role requirement check
        if self.required_role_id:
            role = interaction.guild.get_role(self.required_role_id)
            if role and role not in interaction.user.roles:
                return await interaction.response.send_message(
                    f"You need the {role.mention} role to join this giveaway!",
                    ephemeral=True,
                )

        if interaction.user.id in self.entries:
            return await interaction.response.send_message(
                "You are already participating!", ephemeral=True
            )

        self.entries.append(interaction.user.id)
        update_saved_entries(self.message.id, self.entries)

        embed = interaction.message.embeds[0]
        # Find the Entries field and update it
        for idx, field in enumerate(embed.fields):
            if field.name == "Entries":
                embed.set_field_at(
                    idx, name="Entries", value=str(len(self.entries)), inline=True
                )
                break

        await interaction.response.edit_message(embed=embed, view=self)

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed_log = discord.Embed(
                title="New Giveaway Entry",
                description=f"{interaction.user.mention} has entered the giveaway hosted by {self.host.mention}.",
                color=discord.Color.green(),
                timestamp=datetime.utcnow(),
            )
            await log_channel.send(embed=embed_log)

        # Send DM to host
        try:
            await self.host.send(embed=embed_log)
        except discord.Forbidden:
            pass  # Host has DMs closed


class ConfirmationView(discord.ui.View):
    def __init__(
        self,
        embed: discord.Embed,
        end_time: datetime,
        prizes: list,
        description: str,
        required_role_id: int,
        image_url: str,
    ):
        super().__init__(timeout=300)
        self.embed = embed
        self.end_time = end_time
        self.prizes = prizes
        self.description = description
        self.required_role_id = required_role_id
        self.image_url = image_url

    @discord.ui.button(label="Confirm & Start", style=discord.ButtonStyle.green)
    async def confirm_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="Starting giveaway...", embed=self.embed, view=self
        )

        view = JoinGiveawayButton(
            end_time=self.end_time,
            host=interaction.user,
            prizes=self.prizes,
            description=self.description,
            required_role_id=self.required_role_id,
            image_url=self.image_url,
        )

        # Post the actual giveaway to the channel
        msg = await interaction.channel.send(embed=self.embed, view=view)
        view.message = msg
        view.start_tasks()  # <--- Start nedtellingen her

        # Store view so reroll can find it later
        cog = interaction.client.get_cog("GiveawayCog")
        if cog is not None:
            cog.active_giveaways[str(msg.id)] = view

        # Persist data
        add_saved_giveaway(
            message_id=msg.id,
            channel_id=msg.channel.id,
            guild_id=msg.guild.id,
            end_ts=int(self.end_time.timestamp()),
            host_id=interaction.user.id,
            prizes=self.prizes,
            description=self.description,
            entries=[],
            required_role_id=self.required_role_id,
            image_url=self.image_url,
        )

        role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if role:
            await interaction.channel.send(
                f"{role.mention} 🎉 A new giveaway has started!"
            )

        # Send DM to host that giveaway started
        try:
            start_dm = discord.Embed(
                title="Giveaway Started",
                description="Your giveaway has successfully started!",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow(),
            )
            await interaction.user.send(embed=start_dm)
        except discord.Forbidden:
            pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="Giveaway creation cancelled.", embed=None, view=self
        )


class GiveawayModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Create a Giveaway")

        self.prize_input = discord.ui.TextInput(
            label="Prize(s) (Comma separated)",
            placeholder="e.g. VIP Role, 1000 Coins, Cool Sword",
            required=True,
            max_length=200,
        )
        self.duration_input = discord.ui.TextInput(
            label="Duration",
            placeholder="e.g. 1d, 12h, 30m",
            required=True,
            max_length=50,
        )
        self.description_input = discord.ui.TextInput(
            label="Description (Optional)",
            style=discord.TextStyle.paragraph,
            placeholder="Any extra info you want to add.",
            required=False,
            max_length=500,
        )
        self.role_input = discord.ui.TextInput(
            label="Required Role (Optional)",
            placeholder="Role Name or ID",
            required=False,
            max_length=100,
        )
        self.image_input = discord.ui.TextInput(
            label="Image URL (Optional)",
            placeholder="http://...",
            required=False,
            max_length=250,
        )

        for field in [
            self.prize_input,
            self.duration_input,
            self.description_input,
            self.role_input,
            self.image_input,
        ]:
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Parse Duration
        seconds = parse_duration(self.duration_input.value.strip())
        if seconds <= 0:
            return await interaction.response.send_message(
                "Invalid duration! Please use a format like `1d`, `2h`, or `30m`.",
                ephemeral=True,
            )

        # 2. Parse Prizes
        raw_prizes = [p.strip() for p in self.prize_input.value.split(",")]
        prizes = [p for p in raw_prizes if p]  # Remove empty strings
        if not prizes:
            return await interaction.response.send_message(
                "You must provide at least one valid prize.", ephemeral=True
            )

        # 3. Parse Role Requirement
        required_role_id = None
        if self.role_input.value.strip():
            role_query = self.role_input.value.strip()
            if role_query.isdigit():
                role = interaction.guild.get_role(int(role_query))
            else:
                role = discord.utils.get(interaction.guild.roles, name=role_query)

            if not role:
                return await interaction.response.send_message(
                    f"Could not find a role named/ID `{role_query}`. Please double check.",
                    ephemeral=True,
                )
            required_role_id = role.id

        # 4. Parse Image URL
        image_url = self.image_input.value.strip()
        if image_url and not (
            image_url.startswith("http://") or image_url.startswith("https://")
        ):
            return await interaction.response.send_message(
                "Image URL must start with `http://` or `https://`", ephemeral=True
            )

        end_time = datetime.utcnow() + timedelta(seconds=seconds)
        end_ts = int(end_time.timestamp())

        # Construct Preview Embed
        embed = discord.Embed(
            title="🎉 Giveaway",
            description=self.description_input.value or "No description provided.",
            color=discord.Color.blurple(),
        )

        if image_url:
            embed.set_thumbnail(url=image_url)

        # Format Prize list
        emojis = ["🥇", "🥈", "🥉", "🏅"]
        prize_lines = []
        for idx, p in enumerate(prizes):
            emoji = emojis[idx] if idx < 3 else emojis[-1]
            prize_lines.append(f"{emoji} **{idx + 1}. Place:** {p}")

        embed.add_field(name="Prizes", value="\n".join(prize_lines), inline=False)
        embed.add_field(
            name="Ends", value=f"<t:{end_ts}:R> (<t:{end_ts}:f>)", inline=False
        )
        embed.add_field(name="Hosted by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Entries", value="0", inline=True)
        embed.add_field(name="Winners", value=str(len(prizes)), inline=True)

        if required_role_id:
            role = interaction.guild.get_role(required_role_id)
            embed.add_field(
                name="Requirements", value=f"Must have {role.mention}", inline=False
            )

        view = ConfirmationView(
            embed=embed,
            end_time=end_time,
            prizes=prizes,
            description=self.description_input.value,
            required_role_id=required_role_id,
            image_url=image_url,
        )

        await interaction.response.send_message(
            content="**👀 Preview your giveaway:**\nPlease review the details below. If everything looks correct, press **Confirm & Start**.",
            embed=embed,
            view=view,
            ephemeral=True,
        )


class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.active_giveaways = {}
        self.bot = bot
        self._restored = False

    @app_commands.command(name="giveaway", description="Create a new giveaway.")
    @app_commands.guilds(GUILD_ID)
    async def giveaway_command(self, interaction: discord.Interaction):
        allowed_roles = [OWNER_ROLE_ID, ADMIN_ROLE_ID, GIVEAWAY_STAFF_ROLE_ID]

        if not any(role.id in allowed_roles for role in interaction.user.roles):
            return await interaction.response.send_message(
                "🚫 You don't have permission to start giveaways.", ephemeral=True
            )

        await interaction.response.send_modal(GiveawayModal())

    @app_commands.command(
        name="reroll", description="Reroll winners for an ended giveaway."
    )
    @app_commands.guilds(GUILD_ID)
    @app_commands.describe(message_id="The message ID of the giveaway to reroll")
    async def reroll_command(self, interaction: discord.Interaction, message_id: str):
        allowed_roles = [OWNER_ROLE_ID, ADMIN_ROLE_ID, GIVEAWAY_STAFF_ROLE_ID]

        if not any(role.id in allowed_roles for role in interaction.user.roles):
            return await interaction.response.send_message(
                "🚫 You don't have permission to reroll giveaways.", ephemeral=True
            )

        try:
            msg_id = int(message_id)
        except ValueError:
            return await interaction.response.send_message(
                "Invalid message ID. Please provide a valid number.", ephemeral=True
            )

        # Find the message
        channel = interaction.channel
        try:
            message = await channel.fetch_message(msg_id)
        except discord.NotFound:
            return await interaction.response.send_message(
                "Message not found in this channel.", ephemeral=True
            )
        except Exception as e:
            return await interaction.response.send_message(
                f"Error fetching message: {e}", ephemeral=True
            )

        # Look up the view from active_giveaways
        view = self.active_giveaways.get(str(msg_id))
        if not isinstance(view, JoinGiveawayButton):
            return await interaction.response.send_message(
                "This message is not a known giveaway. The bot may have restarted after it ended.",
                ephemeral=True,
            )

        if not view.ended:
            return await interaction.response.send_message(
                "This giveaway is still active. Cannot reroll.", ephemeral=True
            )

        if not view.entries:
            return await interaction.response.send_message(
                "No entries to reroll.", ephemeral=True
            )

        # Check if user is the host or has permission
        if interaction.user.id != view.host.id and not any(
            role.id in allowed_roles for role in interaction.user.roles
        ):
            return await interaction.response.send_message(
                "Only the host or staff can reroll this giveaway.", ephemeral=True
            )

        # Reroll winners
        participants = list(view.entries)
        random.shuffle(participants)

        emojis = ["🥇", "🥈", "🥉", "🏅"]

        reroll_text_lines = []
        dm_tasks = []

        reroll_text_lines.append(
            "🔄 **Giveaway Rerolled! Here are the new winners:**\n"
        )

        guild = message.guild

        for idx, prize_name in enumerate(view.prizes):
            emoji = emojis[idx] if idx < 3 else emojis[-1]

            if idx < len(participants):
                winner_id = participants[idx]
                winner = guild.get_member(winner_id)

                reroll_text_lines.append(f"{emoji} **{prize_name}**: <@{winner_id}>")

                if winner:
                    dm_embed = discord.Embed(
                        title="🎉 You won a giveaway (rerolled)!",
                        description=f"Congratulations! You won **{prize_name}** in the rerolled giveaway hosted on **{guild.name}**!\n\nPlease create a ticket in {guild.name} to claim your prize.",
                        color=discord.Color.gold(),
                    )
                    dm_tasks.append(winner.send(embed=dm_embed))
            else:
                reroll_text_lines.append(
                    f"{emoji} **{prize_name}**: *Not enough participants*"
                )

        reroll_text = "\n".join(reroll_text_lines)

        await message.channel.send(reroll_text)

        # Send DMs
        for task in dm_tasks:
            try:
                await task
            except discord.Forbidden:
                pass

        # Send DM to host
        try:
            reroll_dm = discord.Embed(
                title="Giveaway Rerolled",
                description=reroll_text,
                color=discord.Color.orange(),
                timestamp=datetime.utcnow(),
            )
            await view.host.send(embed=reroll_dm)
        except discord.Forbidden:
            pass

        await interaction.response.send_message(
            "Giveaway rerolled successfully!", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_ready(self):
        if self._restored:
            return
        self._restored = True

        data = load_saved_giveaways()
        if not data:
            return

        now = datetime.utcnow()

        for key, info in data.items():
            try:
                channel_id = info["channel_id"]
                message_id = info["message_id"]
                end_ts = info["end_ts"]
                host_id = info["host_id"]

                # Compatibility for older saved data vs new structure
                if "prizes" in info:
                    prizes = info["prizes"]
                else:
                    prizes = [info.get("prize", "Unknown Prize")]

                description = info.get("description", "")
                entries = info.get("entries", [])
                required_role_id = info.get("required_role_id")
                image_url = info.get("image_url")

                try:
                    channel = self.bot.get_channel(
                        channel_id
                    ) or await self.bot.fetch_channel(channel_id)
                except Exception:
                    continue

                try:
                    message = await channel.fetch_message(message_id)
                except Exception:
                    remove_saved_giveaway(message_id)
                    continue

                host = None
                try:
                    # Vi prøver å hente som Member først hvis vi kan
                    host = message.guild.get_member(
                        host_id
                    ) or await message.guild.fetch_member(host_id)
                except Exception:
                    try:
                        host = await self.bot.fetch_user(host_id)
                    except Exception:
                        host = message.author

                end_time = datetime.utcfromtimestamp(end_ts)
                view = JoinGiveawayButton(
                    end_time=end_time,
                    host=host,
                    prizes=prizes,
                    description=description,
                    required_role_id=required_role_id,
                    image_url=image_url,
                )
                view.entries = entries
                view.message = message  # Koble til meldingen FØRST

                if end_time <= now:
                    # Hvis tiden allerede er ute, avslutt den med en gang
                    logger.info(
                        f"Giveaway {message.id} expired while offline. Ending now..."
                    )
                    await view.end_giveaway()
                else:
                    # Hvis den fortsatt er aktiv, registrer viewet og start nedtelling
                    try:
                        self.bot.add_view(view, message_id=message.id)
                    except Exception:
                        try:
                            await message.edit(view=view)
                        except Exception:
                            pass

                    view.start_tasks()
                    self.active_giveaways[str(message.id)] = view
                    logger.info(f"Restored giveaway {message.id}")
            except Exception as e:
                logger.error(f"Error while restoring giveaway {key}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
