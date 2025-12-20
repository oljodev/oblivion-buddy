import discord
from discord.ext import commands

GUILD_ID = discord.Object(id=1422932147550818507)


TICKET_CHANNEL_ID = 1422936354404302921

# --- Role IDs ---
OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090
HELPER_ROLE_ID = 1422937956959785040


async def clean_ticket_channel(channel: discord.TextChannel):
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    # Behold første melding (eldste), slett resten
    for msg in messages[1:]:
        await msg.delete()


# --- Ticket Controls (View for Claim/Close) ---
class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # Inne i class TicketControls(discord.ui.View):

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary)
    async def ticket_claim_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):  # ENDRET NAVN HER
        await interaction.response.send_message(
            "✅ Ticket claimed. Thread will be deleted.", ephemeral=True
        )
        await interaction.channel.delete()

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def ticket_close_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "🔒 Ticket closed. Thread will be deleted.", ephemeral=True
        )
        await interaction.channel.delete()


# --- Ticket Panel View (Create Ticket) ---
class TicketPanel(discord.ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.success)
    async def create_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)

        target_channel = self.bot.get_channel(TICKET_CHANNEL_ID)

        if not isinstance(target_channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Error: Could not create thread in this channel. Check TICKET_CHANNEL_ID.",
                ephemeral=True,
            )
            return

        try:
            thread = await target_channel.create_thread(
                name=f"Ticket-{interaction.user.name}",
                type=discord.ChannelType.private_thread,
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error creating thread: {e}", ephemeral=True
            )
            return

        async for msg in thread.history(limit=5):
            if msg.type == discord.MessageType.thread_created:
                await msg.delete()
                break

        owner_role = interaction.guild.get_role(OWNER_ROLE_ID)
        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
        helper_role = interaction.guild.get_role(HELPER_ROLE_ID)

        await clean_ticket_channel(target_channel)

        pings = []
        if owner_role:
            pings.append(owner_role.mention)
        if admin_role:
            pings.append(admin_role.mention)
        if helper_role:
            pings.append(helper_role.mention)

        ping_text = " ".join(pings)

        await thread.send(f"{ping_text} {interaction.user.mention} opened a Ticket!")

        embed = discord.Embed(
            title="Ticket Created",
            description="An admin or helper will assist you shortly.",
            color=discord.Color.dark_gray(),
        )
        await thread.send(embed=embed, view=TicketControls())

        await interaction.followup.send(
            f"✅ Your Ticket has been created! Go to {thread.mention}", ephemeral=True
        )


# --- Tickets Cog ---
class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def on_ready_setup(self):
        """Kjøres fra main.py for å sette opp Ticket Panel og slette meldinger."""
        channel = self.bot.get_channel(TICKET_CHANNEL_ID)
        if channel:
            # Slett alle meldinger i kanalen
            await channel.purge()

            # Send new panel
            embed = discord.Embed(
                title="Need Help, Support or Assistance?",
                description="Click the button below to open a private ticket. Our admins and helpers will be notified and ready to assist you!\n\n**When to create a ticket:**  \n- Questions about the server or mods  \n- Bugs, exploits, or technical issues  \n- Help with other players or gameplay concerns  \n\n**Why use a ticket?**  \n- Private and faster support  \n- Keeps public channels clean  \n- Staff can track and solve issues efficiently  \n\n**Don’t worry!**  \nIt’s always better to open a ticket than ping staff in public channels. We’re here to help!",
                color=discord.Color.dark_blue(),
            )
            # Sender bot-objektet til View
            await channel.send(embed=embed, view=TicketPanel(self.bot))


# --- NØDVENDIG: Setup Funksjon ---
async def setup(bot):
    cog = Tickets(bot)
    await bot.add_cog(cog)
    # Kjør setup-funksjonen for å sikre at panelet er på plass
    await cog.on_ready_setup()
