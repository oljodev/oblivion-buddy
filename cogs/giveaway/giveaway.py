import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import logging
import random
import asyncio
import re
from pathlib import Path
from config import GUILD_ID as _GUILD_ID, Channel, Role
from cogs.giveaway import auto_entry
from cogs._shared.json_store import load_json, save_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Giveaway")


GUILD_ID = discord.Object(id=_GUILD_ID)
OWNER_ROLE_ID = Role.OWNER
ADMIN_ROLE_ID = Role.ADMIN
MEMBER_ROLE_ID = Role.MEMBER
GIVEAWAY_STAFF_ROLE_ID = Role.GIVEAWAY_STAFF
LOG_CHANNEL_ID = Channel.LOG

# Persistence
GIVEAWAYS_FILE = Path(__file__).parent / "giveaways.json"


# Felles atomisk lagring (se cogs/_shared/json_store.py)
_atomic_write = save_json


def load_saved_giveaways():
    try:
        if not GIVEAWAYS_FILE.exists():
            return {}
        return load_json(GIVEAWAYS_FILE, {})
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
    auto_mode: bool = False,
    pending_user_ids: list | None = None,
    auto_required_seconds: int = auto_entry.REQUIRED_SECONDS,
    auto_window_days: int = auto_entry.WINDOW_DAYS,
    auto_send_dm: bool = True,
    auto_show_leave_button: bool = True,
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
        "auto_mode": auto_mode,
        "pending_user_ids": pending_user_ids or [],
        "auto_required_seconds": auto_required_seconds,
        "auto_window_days": auto_window_days,
        "auto_send_dm": auto_send_dm,
        "auto_show_leave_button": auto_show_leave_button,
    }
    save_all_giveaways(data)


def update_saved_entries(message_id: int, entries: list):
    data = load_saved_giveaways()
    key = str(message_id)
    if key in data:
        data[key]["entries"] = entries
        save_all_giveaways(data)


def update_saved_pending(message_id: int, pending_user_ids: list):
    data = load_saved_giveaways()
    key = str(message_id)
    if key in data:
        data[key]["pending_user_ids"] = pending_user_ids
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


def parse_days(value: str) -> int:
    """Parse '7', '7d', '14d' into days. Returns 0 on failure."""
    s = (value or "").strip().lower().rstrip("d").strip()
    if not s.isdigit():
        return 0
    return int(s)


def parse_yes_no(value: str, default: bool = True) -> bool:
    s = (value or "").strip().lower()
    if s in {"yes", "y", "true", "1", "on"}:
        return True
    if s in {"no", "n", "false", "0", "off"}:
        return False
    return default


def format_duration_short(seconds: int) -> str:
    """Render seconds as '1h', '90m', '2h 30m', '1d 4h' for human display."""
    if seconds <= 0:
        return "0m"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and not days:
        parts.append(f"{minutes}m")
    return " ".join(parts) or "0m"


class JoinGiveawayButton(discord.ui.View):
    def __init__(
        self,
        end_time,
        host,
        prizes: list,
        description: str,
        required_role_id: int = None,
        image_url: str = None,
        auto_mode: bool = False,
        auto_required_seconds: int = auto_entry.REQUIRED_SECONDS,
        auto_window_days: int = auto_entry.WINDOW_DAYS,
        auto_send_dm: bool = True,
        auto_show_leave_button: bool = True,
    ):
        super().__init__(timeout=None)
        self.entries = []
        self.pending_user_ids: list[int] = []
        self.end_time = end_time
        self.host = host
        self.prizes = prizes
        self.description = description
        self.required_role_id = required_role_id
        self.image_url = image_url
        self.auto_mode = auto_mode
        self.auto_required_seconds = auto_required_seconds
        self.auto_window_days = auto_window_days
        self.auto_send_dm = auto_send_dm
        self.auto_show_leave_button = auto_show_leave_button
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

        if interaction.user.id in self.entries:
            return await interaction.response.send_message(
                "You are already participating!", ephemeral=True
            )

        # Role requirement check (applies in both modes)
        if self.required_role_id:
            role = interaction.guild.get_role(self.required_role_id)
            if role and role not in interaction.user.roles:
                return await interaction.response.send_message(
                    f"You need the {role.mention} role to join this giveaway!",
                    ephemeral=True,
                )

        if self.auto_mode:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._handle_auto_join(interaction)
            return

        # Standard mode — add immediately.
        self._add_entry(interaction.user.id)
        await self._refresh_message_embed(interaction)
        await self._log_and_dm_host(interaction.user, interaction.guild)

    async def _handle_auto_join(self, interaction: discord.Interaction):
        user = interaction.user
        result = await auto_entry.evaluate_user(
            user.id,
            required_seconds=self.auto_required_seconds,
            window_days=self.auto_window_days,
        )

        if result["qualifies"]:
            self._add_entry(user.id)
            if user.id in self.pending_user_ids:
                self.pending_user_ids.remove(user.id)
                update_saved_pending(self.message.id, self.pending_user_ids)
            await self._refresh_message_embed(interaction, edit_original=False)
            await interaction.followup.send(
                embed=self._build_qualified_embed(result),
                ephemeral=True,
            )
            await self._send_auto_entry_dm(user, result)
            await self._log_and_dm_host(user, interaction.guild)
            return

        # Not qualified yet — register intent.
        if user.id not in self.pending_user_ids:
            self.pending_user_ids.append(user.id)
            update_saved_pending(self.message.id, self.pending_user_ids)

        await interaction.followup.send(
            embed=self._build_status_embed(user, result),
            ephemeral=True,
        )

    def _add_entry(self, user_id: int):
        if user_id not in self.entries:
            self.entries.append(user_id)
            update_saved_entries(self.message.id, self.entries)

    async def _refresh_message_embed(
        self, interaction: discord.Interaction, edit_original: bool = True
    ):
        try:
            msg = self.message
            embed = msg.embeds[0] if msg.embeds else None
            if embed is None:
                return
            for idx, field in enumerate(embed.fields):
                if field.name == "Entries":
                    embed.set_field_at(
                        idx, name="Entries", value=str(len(self.entries)), inline=True
                    )
                    break
            if edit_original and not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await msg.edit(embed=embed, view=self)
        except Exception as e:
            logger.warning(f"Could not refresh giveaway embed: {e}")

    async def _log_and_dm_host(self, user: discord.abc.User, guild: discord.Guild):
        log_channel = guild.get_channel(LOG_CHANNEL_ID) if guild else None
        embed_log = discord.Embed(
            title="New Giveaway Entry",
            description=f"{user.mention} has entered the giveaway hosted by {self.host.mention}.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        if log_channel:
            try:
                await log_channel.send(embed=embed_log)
            except Exception:
                pass
        try:
            await self.host.send(embed=embed_log)
        except discord.Forbidden:
            pass

    def _build_status_embed(self, user, result: dict) -> discord.Embed:
        linked = result["linked"]
        secs = result["seconds_in_window"]
        minutes = secs // 60
        def check(ok: bool) -> str:
            return "✅" if ok else "❌"

        playtime_str = (
            f"{minutes} minutes" if result["current_ticks"] is not None
            else "could not query (try again later)"
        )
        req_str = format_duration_short(self.auto_required_seconds)
        win_str = f"{self.auto_window_days} days"
        lines = [
            f"{check(linked)} **1.** Link your Minecraft account with `/link`.",
            f"{check(secs >= self.auto_required_seconds)} **2.** Play at least {req_str} on the SMP in the last {win_str}. — Your playtime: **{playtime_str}**",
        ]
        if self.required_role_id:
            role_ok = False
            try:
                if user.guild and user.guild.get_role(self.required_role_id) in getattr(user, "roles", []):
                    role_ok = True
            except Exception:
                pass
            lines.append(
                f"{check(role_ok)} **3.** Have the <@&{self.required_role_id}> role."
            )
        lines.append(
            "\nYou're on the waitlist. As soon as you meet the requirements, "
            "the bot will automatically add you and DM you."
        )
        return discord.Embed(
            title="Auto-entry — almost there!",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )

    def _build_qualified_embed(self, result: dict) -> discord.Embed:
        minutes = result["seconds_in_window"] // 60
        return discord.Embed(
            title="🎉 You're entered!",
            description=(
                f"You've been auto-entered into this giveaway because you meet "
                f"the requirements (linked account, **{minutes} minutes** of "
                f"playtime in the last {self.auto_window_days} days)."
            ),
            color=discord.Color.green(),
        )

    async def _send_auto_entry_dm(self, user, result: dict):
        if not self.auto_send_dm:
            return
        try:
            description = (
                f"You've been automatically entered into the giveaway hosted on "
                f"**{self.message.guild.name}** because you completed the "
                f"requirements (linked Minecraft account + "
                f"**{result['seconds_in_window'] // 60} minutes** of playtime "
                f"in the last {self.auto_window_days} days)."
            )
            if self.auto_show_leave_button:
                description += "\n\nIf you don't want to participate, click **Leave giveaway** below."
            embed = discord.Embed(
                title="✅ Auto-entered into a giveaway",
                description=description,
                color=discord.Color.green(),
            )
            if self.auto_show_leave_button:
                view = LeaveGiveawayView(self.message.id)
                await user.send(embed=embed, view=view)
            else:
                await user.send(embed=embed)
        except discord.Forbidden:
            logger.info(f"Cannot DM {user} (id={user.id}): DMs disabled.")
        except Exception as e:
            logger.error(f"Failed to DM auto-entry to {user.id}: {e}")


class LeaveGiveawayView(discord.ui.View):
    """Persistent view sent in the auto-entry DM with a single 'Leave' button.

    Custom ID embeds the giveaway message_id so the cog can route the click
    to the right giveaway after a bot restart.
    """

    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.add_item(LeaveGiveawayButton(message_id))


class LeaveGiveawayButton(discord.ui.Button):
    def __init__(self, message_id: int):
        super().__init__(
            label="Leave giveaway",
            style=discord.ButtonStyle.red,
            custom_id=f"leave_giveaway:{message_id}",
        )
        self.message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("GiveawayCog")
        if cog is None:
            return await interaction.response.send_message(
                "Bot is not ready, try again in a moment.", ephemeral=True
            )
        view = cog.active_giveaways.get(str(self.message_id))
        user_id = interaction.user.id

        if not isinstance(view, JoinGiveawayButton):
            # Giveaway not active in memory — fall back to JSON.
            data = load_saved_giveaways()
            entry = data.get(str(self.message_id))
            if not entry:
                return await interaction.response.send_message(
                    "This giveaway no longer exists.", ephemeral=True
                )
            if user_id in entry.get("entries", []):
                entry["entries"] = [u for u in entry["entries"] if u != user_id]
                save_all_giveaways(data)
            self.disabled = True
            return await interaction.response.edit_message(
                content="You have been removed from the giveaway.", view=self.view
            )

        if view.ended:
            return await interaction.response.send_message(
                "This giveaway has already ended.", ephemeral=True
            )
        if user_id in view.entries:
            view.entries.remove(user_id)
            update_saved_entries(view.message.id, view.entries)
            try:
                msg = view.message
                embed = msg.embeds[0] if msg.embeds else None
                if embed:
                    for idx, field in enumerate(embed.fields):
                        if field.name == "Entries":
                            embed.set_field_at(
                                idx, name="Entries", value=str(len(view.entries)), inline=True
                            )
                            break
                    await msg.edit(embed=embed, view=view)
            except Exception as e:
                logger.warning(f"Could not refresh embed after leave: {e}")
        self.disabled = True
        await interaction.response.edit_message(
            content="You have been removed from the giveaway.", view=self.view
        )


class ChangeAutoSettingsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Change auto settings",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AutoSettingsModal(self.view))


class AutoSettingsModal(discord.ui.Modal):
    def __init__(self, conf_view: "ConfirmationView"):
        super().__init__(title="Auto-entry settings")
        self.conf_view = conf_view

        self.playtime_input = discord.ui.TextInput(
            label="Required playtime",
            placeholder="e.g. 1h, 30m, 2h",
            required=True,
            max_length=20,
            default=format_duration_short(conf_view.auto_required_seconds),
        )
        self.window_input = discord.ui.TextInput(
            label="Time window (days)",
            placeholder="e.g. 7, 14, 30",
            required=True,
            max_length=10,
            default=f"{conf_view.auto_window_days}d",
        )
        self.send_dm_input = discord.ui.TextInput(
            label="Send DM on auto-entry?",
            placeholder="yes / no",
            required=True,
            max_length=10,
            default="yes" if conf_view.auto_send_dm else "no",
        )
        self.leave_button_input = discord.ui.TextInput(
            label="Show 'Leave giveaway' button in DM?",
            placeholder="yes / no",
            required=True,
            max_length=10,
            default="yes" if conf_view.auto_show_leave_button else "no",
        )
        for f in (
            self.playtime_input,
            self.window_input,
            self.send_dm_input,
            self.leave_button_input,
        ):
            self.add_item(f)

    async def on_submit(self, interaction: discord.Interaction):
        seconds = parse_duration(self.playtime_input.value)
        if seconds <= 0:
            return await interaction.response.send_message(
                "Invalid playtime — use formats like `1h`, `30m`, `2h 30m`.",
                ephemeral=True,
            )
        days = parse_days(self.window_input.value)
        if days <= 0:
            return await interaction.response.send_message(
                "Invalid time window — use a positive number of days like `7` or `14d`.",
                ephemeral=True,
            )

        self.conf_view.auto_required_seconds = seconds
        self.conf_view.auto_window_days = days
        self.conf_view.auto_send_dm = parse_yes_no(
            self.send_dm_input.value, default=True
        )
        self.conf_view.auto_show_leave_button = parse_yes_no(
            self.leave_button_input.value, default=True
        )

        # Rebuild the preview embed to reflect the new settings.
        new_embed = self.conf_view.build_embed()
        self.conf_view.embed = new_embed
        await interaction.response.edit_message(
            content=(
                "**👀 Preview your giveaway:**\n"
                "Auto settings updated. Press **Confirm & Start** when ready."
            ),
            embed=new_embed,
            view=self.conf_view,
        )


class ConfirmationView(discord.ui.View):
    def __init__(
        self,
        embed: discord.Embed,
        end_time: datetime,
        prizes: list,
        description: str,
        required_role_id: int,
        image_url: str,
        auto_mode: bool = False,
        host_mention: str = "",
        auto_required_seconds: int = auto_entry.REQUIRED_SECONDS,
        auto_window_days: int = auto_entry.WINDOW_DAYS,
        auto_send_dm: bool = True,
        auto_show_leave_button: bool = True,
    ):
        super().__init__(timeout=300)
        self.embed = embed
        self.end_time = end_time
        self.prizes = prizes
        self.description = description  # plain (no auto-mode block appended)
        self.required_role_id = required_role_id
        self.image_url = image_url
        self.auto_mode = auto_mode
        self.host_mention = host_mention
        self.auto_required_seconds = auto_required_seconds
        self.auto_window_days = auto_window_days
        self.auto_send_dm = auto_send_dm
        self.auto_show_leave_button = auto_show_leave_button
        if self.auto_mode:
            self.add_item(ChangeAutoSettingsButton())

    def build_embed(self) -> discord.Embed:
        """Reconstruct the preview embed using current settings."""
        end_ts = int(self.end_time.timestamp())
        req_str = format_duration_short(self.auto_required_seconds)
        win_str = f"{self.auto_window_days} days"

        base_description = self.description or "No description provided."
        if self.auto_mode:
            base_description = (
                f"{base_description}\n\n"
                "**🤖 Auto-entry mode**\n"
                "Click **🎉 Join** and follow the instructions:\n"
                "1. Link your Minecraft account with `/link` (if you haven't already).\n"
                f"2. Play at least **{req_str}** on the SMP in the last **{win_str}**.\n"
                "3. Once you meet the requirements, you'll be added automatically"
                + (" and DM'd." if self.auto_send_dm else ".")
            )

        embed = discord.Embed(
            title="🎉 Giveaway",
            description=base_description,
            color=discord.Color.blurple(),
        )
        if self.image_url:
            embed.set_thumbnail(url=self.image_url)

        emojis = ["🥇", "🥈", "🥉", "🏅"]
        prize_lines = []
        for idx, p in enumerate(self.prizes):
            emoji = emojis[idx] if idx < 3 else emojis[-1]
            prize_lines.append(f"{emoji} **{idx + 1}. Place:** {p}")
        embed.add_field(name="Prizes", value="\n".join(prize_lines), inline=False)
        embed.add_field(
            name="Ends", value=f"<t:{end_ts}:R> (<t:{end_ts}:f>)", inline=False
        )
        embed.add_field(name="Hosted by", value=self.host_mention, inline=True)
        embed.add_field(name="Entries", value="0", inline=True)
        embed.add_field(name="Winners", value=str(len(self.prizes)), inline=True)

        req_lines = []
        if self.auto_mode:
            req_lines.append(
                f"Auto-entry: linked MC account + {req_str} playtime in last {win_str}"
            )
        if self.required_role_id:
            req_lines.append(f"Must have <@&{self.required_role_id}>")
        if req_lines:
            embed.add_field(name="Requirements", value="\n".join(req_lines), inline=False)

        return embed

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
            auto_mode=self.auto_mode,
            auto_required_seconds=self.auto_required_seconds,
            auto_window_days=self.auto_window_days,
            auto_send_dm=self.auto_send_dm,
            auto_show_leave_button=self.auto_show_leave_button,
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
            auto_mode=self.auto_mode,
            pending_user_ids=[],
            auto_required_seconds=self.auto_required_seconds,
            auto_window_days=self.auto_window_days,
            auto_send_dm=self.auto_send_dm,
            auto_show_leave_button=self.auto_show_leave_button,
        )

        # Register persistent leave view so the DM button works after restart.
        try:
            interaction.client.add_view(LeaveGiveawayView(msg.id))
        except Exception as e:
            logger.warning(f"Could not register leave view for {msg.id}: {e}")

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
            placeholder="Role Name/ID, 'auto', or 'auto + RoleName'",
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

        # 3. Parse Role Requirement (and optional 'auto' keyword for auto-entry mode)
        auto_mode, role_query = auto_entry.parse_role_field(self.role_input.value)
        required_role_id = None
        if role_query:
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

        raw_description = self.description_input.value or "No description provided."

        view = ConfirmationView(
            embed=None,  # built below
            end_time=end_time,
            prizes=prizes,
            description=raw_description,
            required_role_id=required_role_id,
            image_url=image_url,
            auto_mode=auto_mode,
            host_mention=interaction.user.mention,
        )
        embed = view.build_embed()
        view.embed = embed

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
        self.snapshot_loop.start()
        self.recheck_pending_loop.start()

    def cog_unload(self):
        self.snapshot_loop.cancel()
        self.recheck_pending_loop.cancel()

    @tasks.loop(hours=1)
    async def snapshot_loop(self):
        try:
            count = await auto_entry.snapshot_all_linked()
            if count:
                logger.info(f"Recorded playtime snapshots for {count} linked user(s).")
        except Exception as e:
            logger.error(f"Snapshot loop error: {e}")

    @snapshot_loop.before_loop
    async def _before_snapshot(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=15)
    async def recheck_pending_loop(self):
        try:
            for msg_id, view in list(self.active_giveaways.items()):
                if not isinstance(view, JoinGiveawayButton):
                    continue
                if view.ended or not view.auto_mode or not view.pending_user_ids:
                    continue
                guild = view.message.guild if hasattr(view, "message") else None
                if guild is None:
                    continue
                # Snapshot taken inside evaluate_user; iterate a copy.
                for user_id in list(view.pending_user_ids):
                    member = guild.get_member(user_id)
                    if member is None:
                        view.pending_user_ids.remove(user_id)
                        update_saved_pending(view.message.id, view.pending_user_ids)
                        continue
                    # Re-check role requirement first (cheap, no RCON).
                    if view.required_role_id:
                        role = guild.get_role(view.required_role_id)
                        if role and role not in member.roles:
                            continue
                    result = await auto_entry.evaluate_user(
                        user_id,
                        required_seconds=view.auto_required_seconds,
                        window_days=view.auto_window_days,
                    )
                    if not result["qualifies"]:
                        continue
                    view._add_entry(user_id)
                    view.pending_user_ids.remove(user_id)
                    update_saved_pending(view.message.id, view.pending_user_ids)
                    try:
                        msg = view.message
                        embed = msg.embeds[0] if msg.embeds else None
                        if embed:
                            for idx, field in enumerate(embed.fields):
                                if field.name == "Entries":
                                    embed.set_field_at(
                                        idx, name="Entries",
                                        value=str(len(view.entries)), inline=True,
                                    )
                                    break
                            await msg.edit(embed=embed, view=view)
                    except Exception as e:
                        logger.warning(f"Could not refresh embed during recheck: {e}")
                    await view._send_auto_entry_dm(member, result)
                    await view._log_and_dm_host(member, guild)
                    logger.info(
                        f"Auto-added pending user {user_id} to giveaway {view.message.id}."
                    )
        except Exception as e:
            logger.error(f"Recheck pending loop error: {e}")

    @recheck_pending_loop.before_loop
    async def _before_recheck(self):
        await self.bot.wait_until_ready()

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
                auto_mode = info.get("auto_mode", False)
                pending_user_ids = info.get("pending_user_ids", [])
                auto_required_seconds = info.get(
                    "auto_required_seconds", auto_entry.REQUIRED_SECONDS
                )
                auto_window_days = info.get(
                    "auto_window_days", auto_entry.WINDOW_DAYS
                )
                auto_send_dm = info.get("auto_send_dm", True)
                auto_show_leave_button = info.get("auto_show_leave_button", True)

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
                    auto_mode=auto_mode,
                    auto_required_seconds=auto_required_seconds,
                    auto_window_days=auto_window_days,
                    auto_send_dm=auto_send_dm,
                    auto_show_leave_button=auto_show_leave_button,
                )
                view.entries = entries
                view.pending_user_ids = list(pending_user_ids)
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
                    if auto_mode:
                        try:
                            self.bot.add_view(LeaveGiveawayView(message.id))
                        except Exception as e:
                            logger.warning(
                                f"Could not register leave view for restored giveaway {message.id}: {e}"
                            )
                    logger.info(f"Restored giveaway {message.id}")
            except Exception as e:
                logger.error(f"Error while restoring giveaway {key}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
