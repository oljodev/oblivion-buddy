import discord
from discord.ext import commands
import logging
from config import Channel, Role
LOG_CHANNEL_ID = Channel.MODERATION
BOT_ROLE_ID = Role.BOT

logger = logging.getLogger(__name__)


class DeclineDropdown(discord.ui.Select):
    def __init__(self, target_bot: discord.Member, original_message: discord.Message):
        self.target_bot = target_bot
        self.original_message = original_message

        options = [
            discord.SelectOption(
                label="Ban", description="Permanently ban the app", emoji="🔨"
            ),
            discord.SelectOption(
                label="Kick", description="Remove the app from the server", emoji="👢"
            ),
            discord.SelectOption(
                label="Do Nothing",
                description="Keep the app with zero access",
                emoji="⏹️",
            ),
        ]
        super().__init__(
            placeholder="Choose an action...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        result_text = ""

        try:
            if choice == "Ban":
                await self.target_bot.ban(reason="App declined by administrator.")
                result_text = f"🔨 {interaction.user.mention} decided to **Ban** {self.target_bot.name}."
            elif choice == "Kick":
                await self.target_bot.kick(reason="App declined by administrator.")
                result_text = f"👢 {interaction.user.mention} decided to **Kick** {self.target_bot.name}."
            else:
                result_text = f"⏹️ {interaction.user.mention} chose **No Action** for {self.target_bot.mention} (remains restricted)."

            # Update the original embed to disable buttons
            view = discord.ui.View.from_message(self.original_message)
            for item in view.children:
                item.disabled = True
            await self.original_message.edit(view=view)

            # Post the result publicly in the channel
            await interaction.channel.send(result_text)
            await interaction.response.send_message("Action completed.", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)


class DeclineView(discord.ui.View):
    def __init__(self, target_bot: discord.Member, original_message: discord.Message):
        super().__init__(timeout=60)
        self.add_item(DeclineDropdown(target_bot, original_message))


class BotVerificationView(discord.ui.View):
    def __init__(self, target_bot: discord.Member):
        super().__init__(timeout=None)  # Keeps buttons functional after bot restart
        self.target_bot = target_bot

    @discord.ui.button(label="Approve (Bot Role)", style=discord.ButtonStyle.green)
    async def approve(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        role = interaction.guild.get_role(BOT_ROLE_ID)
        if role:
            await self.target_bot.add_roles(role)
            await interaction.response.send_message(
                f"✅ {self.target_bot.mention} has been assigned the Bot role.",
                ephemeral=False,
            )

            # Disable buttons after use
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message(
                "Error: Could not find Bot Role ID.", ephemeral=True
            )

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Sends the dropdown menu as an ephemeral message only visible to the admin
        view = DeclineView(self.target_bot, interaction.message)
        await interaction.response.send_message(
            "Select an action for this app:", view=view, ephemeral=True
        )


class BotManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            log_channel = member.guild.get_channel(LOG_CHANNEL_ID)

            # Finn alle roller boten fikk ved inngang (utenom @everyone)
            roles_to_remove = [
                role for role in member.roles if role != member.guild.default_role
            ]

            if roles_to_remove:
                try:
                    # Fjern alle roller umiddelbart for å "nøytralisere" boten
                    await member.remove_roles(
                        *roles_to_remove, reason="Neutralizing new app until approved."
                    )
                    status_msg = (
                        f"🛡️ Stripped all roles from **{member.name}** pending approval."
                    )
                    if log_channel:
                        await log_channel.send(status_msg)

                    logger.info(
                        f"Stripped all roles from {member.name} pending approval."
                    )

                except discord.Forbidden:
                    error_msg = f"⚠️ Could not strip roles from **{member.name}**. My role is likely too low in the hierarchy!"
                    if log_channel:
                        await log_channel.send(error_msg)

                    logger.error(
                        f"Could not strip roles from {member.name}. My role might be too low!"
                    )
                    # Ensure your @everyone role has "View Channels" turned OFF for this to mean "Zero Access"

            if log_channel:
                embed = discord.Embed(
                    title="🤖 New App Detected",
                    description=f"The app **{member.name}** ({member.mention}) has joined the server.\n\nShould this app be granted access?",
                    color=discord.Color.blue(),
                )
                if member.avatar:
                    embed.set_thumbnail(url=member.avatar.url)

                view = BotVerificationView(member)
                await log_channel.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(BotManager(bot))
