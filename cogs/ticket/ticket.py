import asyncio
import logging
import discord
from discord.ext import commands
from pathlib import Path
import json
from config import Channel, Role

log = logging.getLogger(__name__)
TICKET_CHANNEL_ID = Channel.TICKET
OWNER_ROLE_ID = Role.OWNER
ADMIN_ROLE_ID = Role.ADMIN
HELPER_ROLE_ID = Role.HELPER
GIVEAWAY_STAFF_ROLE_ID = Role.GIVEAWAY_STAFF

DATA_FILE = Path(__file__).parent / "tickets.json"


# --- JSON Helpers ---
def load_data():
    if not DATA_FILE.exists():
        return {"panel_message_id": None, "active_threads": []}
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"panel_message_id": None, "active_threads": []}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


# --- Modals ---
class TicketModal(discord.ui.Modal):
    def __init__(self, title, reason_type):
        super().__init__(title=title)
        self.reason_type = reason_type

        # dynamic fields based on selection
        if reason_type == "Report":
            self.add_item(
                discord.ui.TextInput(
                    label="Who are you reporting?",
                    placeholder="Username...",
                    required=True,
                )
            )
            self.add_item(
                discord.ui.TextInput(
                    label="What happened?",
                    style=discord.TextStyle.paragraph,
                    required=True,
                )
            )
            self.add_item(
                discord.ui.TextInput(
                    label="When did it happen?",
                    placeholder="e.g. 10 minutes ago",
                    required=False,
                )
            )
            self.add_item(
                discord.ui.TextInput(
                    label="Coordinates/Location",
                    placeholder="X: 100, Y: 64, Z: -500",
                    required=False,
                )
            )
        elif reason_type == "Technical":
            self.add_item(
                discord.ui.TextInput(
                    label="What is the issue?",
                    placeholder="Describe the bug/error...",
                    style=discord.TextStyle.paragraph,
                    required=True,
                )
            )
        else:
            self.add_item(
                discord.ui.TextInput(
                    label="Subject", placeholder="Brief summary...", required=True
                )
            )
            self.add_item(
                discord.ui.TextInput(
                    label="Details", style=discord.TextStyle.paragraph, required=True
                )
            )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # 1. Create the thread
        target_channel = interaction.guild.get_channel(TICKET_CHANNEL_ID)
        thread = await target_channel.create_thread(
            name=f"{self.reason_type}-{interaction.user.name}",
            type=discord.ChannelType.private_thread,
        )

        # 2. Save to JSON
        data = load_data()
        data["active_threads"].append(thread.id)
        save_data(data)

        # 3. Build the Summary Embed
        embed = discord.Embed(
            title=f"New Ticket: {self.reason_type}", color=discord.Color.green()
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )

        for item in self.children:
            embed.add_field(
                name=item.label, value=item.value or "Not provided", inline=False
            )

        # 4. Pings
        pings = " ".join(
            [
                f"<@&{r}>"
                for r in [OWNER_ROLE_ID, ADMIN_ROLE_ID, HELPER_ROLE_ID]
                if interaction.guild.get_role(r)
            ]
        )

        await thread.send(
            content=f"{pings} {interaction.user.mention}",
            embed=embed,
            view=TicketControls(),
        )

        if self.reason_type == "Technical":
            await thread.send(
                "**AI Assistant available!**\n"
                "While you wait for staff, you can try asking our AI for help:\n"
                "1. Type `!ai` followed by your question\n"
                "2. Attach your screenshot or crash log to the same message\n\n"
                "**Example:** `!ai I get a crash when joining` *(+ attach screenshot)*"
            )

        await interaction.followup.send(
            f"✅ Ticket created! Go here: {thread.mention}", ephemeral=True
        )


class ClaimGiveawayModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Claim Giveaway")
        self.reason_type = "ClaimGiveaway"

        self.add_item(
            discord.ui.TextInput(
                label="Your Prize",
                placeholder="What did you win?",
                required=True,
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # 1. Create the thread
        target_channel = interaction.guild.get_channel(TICKET_CHANNEL_ID)
        thread = await target_channel.create_thread(
            name=f"{self.reason_type}-{interaction.user.name}",
            type=discord.ChannelType.private_thread,
        )

        # 2. Save to JSON
        data = load_data()
        data["active_threads"].append(thread.id)
        save_data(data)

        # 3. Build the Summary Embed
        embed = discord.Embed(
            title=f"New Ticket: {self.reason_type}", color=discord.Color.green()
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )

        for item in self.children:
            embed.add_field(
                name=item.label, value=item.value or "Not provided", inline=False
            )

        # 4. Pings
        pings = " ".join(
            [
                f"<@&{r}>"
                for r in [OWNER_ROLE_ID, ADMIN_ROLE_ID, GIVEAWAY_STAFF_ROLE_ID]
                if interaction.guild.get_role(r)
            ]
        )
        await thread.send(
            content=f"{pings} {interaction.user.mention}",
            embed=embed,
            view=TicketControls(),
        )
        await interaction.followup.send(
            f"✅ Ticket created! Go here: {thread.mention}", ephemeral=True
        )


class ReportBotBugModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Report Bot Bug")
        self.reason_type = "ReportBotBug"

        self.add_item(
            discord.ui.TextInput(
                label="Bug Description",
                placeholder="Describe the bug/error...",
                style=discord.TextStyle.paragraph,
                required=True,
            )
        )
        self.add_item(
            discord.ui.TextInput(
                label="Feature Affected",
                placeholder="Which feature was affected?",
                required=True,
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # 1. Create the thread
        target_channel = interaction.guild.get_channel(TICKET_CHANNEL_ID)
        thread = await target_channel.create_thread(
            name=f"{self.reason_type}-{interaction.user.name}",
            type=discord.ChannelType.private_thread,
        )

        # 2. Save to JSON
        data = load_data()
        data["active_threads"].append(thread.id)
        save_data(data)

        # 3. Build the Summary Embed
        embed = discord.Embed(
            title=f"New Ticket: {self.reason_type}", color=discord.Color.green()
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )

        for item in self.children:
            embed.add_field(
                name=item.label, value=item.value or "Not provided", inline=False
            )

        # 4. Pings
        pings = " ".join(
            [
                f"<@&{r}>"
                for r in [OWNER_ROLE_ID, ADMIN_ROLE_ID, HELPER_ROLE_ID]
                if interaction.guild.get_role(r)
            ]
        )

        await thread.send(
            content=f"{pings} {interaction.user.mention}",
            embed=embed,
            view=TicketControls(),
        )
        await thread.send("Please upload a screenshot of the error.")
        await interaction.followup.send(
            f"✅ Ticket created! Go here: {thread.mention}", ephemeral=True
        )


class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Report a Player",
                description="Stealing, Griefing, Rule Breaking",
                emoji="🛡️",
                value="Report",
            ),
            discord.SelectOption(
                label="General Support",
                description="Questions about the server",
                emoji="❓",
                value="Support",
            ),
            discord.SelectOption(
                label="Technical Issue",
                description="Bugs, Lag, Connection errors",
                emoji="⚙️",
                value="Technical",
            ),
            discord.SelectOption(
                label="Claim Giveaway",
                description="Claim a giveaway prize",
                emoji="🎉",
                value="ClaimGiveaway",
            ),
            discord.SelectOption(
                label="Report Bot Bug",
                description="Report a bug with Oblivion Buddy",
                emoji="🐛",
                value="ReportBotBug",
            ),
            discord.SelectOption(
                label="Other", description="Anything else", emoji="📝", value="Other"
            ),
        ]
        super().__init__(
            placeholder="Choose the reason for your ticket...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "Report":
            await interaction.response.send_modal(
                TicketModal("Report Player", "Report")
            )
        elif self.values[0] == "Technical":
            await interaction.response.send_modal(
                TicketModal("Technical Support", "Technical")
            )
        elif self.values[0] == "ClaimGiveaway":
            await interaction.response.send_modal(ClaimGiveawayModal())
        elif self.values[0] == "ReportBotBug":
            await interaction.response.send_modal(ReportBotBugModal())
        else:
            await interaction.response.send_modal(
                TicketModal("Support Ticket", self.values[0])
            )


class TicketSelectionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())


# --- Thread cleanup helpers ---
async def _remove_from_active(thread_id: int) -> None:
    data = load_data()
    if thread_id in data.get("active_threads", []):
        data["active_threads"].remove(thread_id)
        save_data(data)


async def _delete_ticket_thread(thread: discord.Thread) -> None:
    # Small delay so the acknowledging message has a chance to deliver before
    # the channel disappears.
    await asyncio.sleep(1)
    try:
        await thread.delete()
        return
    except discord.Forbidden:
        log.error(
            "Missing permission to delete ticket thread %s (%s) — falling back to archive+lock",
            thread.id,
            thread.name,
        )
    except discord.HTTPException:
        log.exception("Failed to delete ticket thread %s (%s)", thread.id, thread.name)

    try:
        await thread.edit(archived=True, locked=True)
    except discord.HTTPException:
        log.exception("Failed to archive/lock ticket thread %s", thread.id)


# --- Persistence ---
class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim", style=discord.ButtonStyle.primary, custom_id="claim_v2"
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(
            f"✅ Ticket claimed by {interaction.user.mention}. Deleting…"
        )
        await interaction.response.defer()
        await _remove_from_active(interaction.channel.id)
        await _delete_ticket_thread(interaction.channel)

    @discord.ui.button(
        label="Close", style=discord.ButtonStyle.danger, custom_id="close_v2"
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await _remove_from_active(interaction.channel.id)
        await _delete_ticket_thread(interaction.channel)


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Create Ticket",
        style=discord.ButtonStyle.success,
        custom_id="open_panel_v2",
    )
    async def create_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Step 1: Send the ephemeral dropdown
        await interaction.response.send_message(
            "Please select the reason for your ticket below:",
            view=TicketSelectionView(),
            ephemeral=True,
        )


# --- Cog ---
class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_main_panel(self, channel):
        embed = discord.Embed(
            title="Need Help, Support or Assistance?",
            description=(
                "Click the button below to open a private ticket. Our admins and helpers will be notified and ready to assist you!\n\n"
                "**When to create a ticket:**\n"
                "- Questions about the server or mods\n"
                "- Bugs, exploits, or technical issues\n"
                "- General question to the staff team\n"
                "- Help with other players or gameplay concerns\n\n"
                "**Why use a ticket?**\n"
                "- Private and faster support\n"
                "- Keeps public channels clean\n"
                "- Staff can track and solve issues efficiently\n\n"
                "**Don’t worry!**\n"
                "It’s always better to open a ticket than ping staff in public channels. We’re here to help!"
            ),
            color=discord.Color.dark_blue(),
        )
        msg = await channel.send(embed=embed, view=TicketPanel())
        data = load_data()
        data["panel_message_id"] = msg.id
        save_data(data)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketPanel())
        self.bot.add_view(TicketControls())

        channel = self.bot.get_channel(TICKET_CHANNEL_ID)
        if not channel:
            return

        data = load_data()
        is_empty = True
        async for _ in channel.history(limit=1):
            is_empty = False
            break

        if is_empty or not data.get("panel_message_id"):
            await self.send_main_panel(channel)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        data = load_data()
        if message.id == data.get("panel_message_id"):
            await self.send_main_panel(message.channel)


async def setup(bot):
    await bot.add_cog(Tickets(bot))
