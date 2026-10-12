import discord
from discord.ext import commands
import logging
from config import Channel, Role
LOG_CHANNEL_ID = Channel.MODERATION
BOT_ROLE_ID = Role.BOT
REVIEWER_ROLE_IDS = {Role.OWNER, Role.ADMIN}

logger = logging.getLogger(__name__)


def is_app_reviewer(member) -> bool:
    """Bare eiere/admins (eller de med Administrator) kan godkjenne/avvise apper."""
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    return any(r.id in REVIEWER_ROLE_IDS for r in member.roles)


async def deny_if_not_reviewer(interaction: discord.Interaction) -> bool:
    """Svarer med en feilmelding og returnerer True hvis brukeren ikke har tilgang."""
    if is_app_reviewer(interaction.user):
        return False
    await interaction.response.send_message(
        "🚫 Only the server owner or admins can review apps.", ephemeral=True
    )
    return True


def verification_view(app_id: int, *, disabled: bool = False) -> discord.ui.View:
    """Approve/Decline-knappene. App-ID-en ligger i custom_id, så de virker etter restart."""
    view = discord.ui.View(timeout=None)
    approve, decline = ApproveButton(app_id), DeclineButton(app_id)
    approve.item.disabled = decline.item.disabled = disabled
    view.add_item(approve)
    view.add_item(decline)
    return view


class ApproveButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"app_verify:approve:(?P<id>[0-9]+)"
):
    def __init__(self, app_id: int):
        super().__init__(
            discord.ui.Button(
                label="Approve (Bot Role)",
                style=discord.ButtonStyle.green,
                custom_id=f"app_verify:approve:{app_id}",
            )
        )
        self.app_id = app_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        if await deny_if_not_reviewer(interaction):
            return
        target = interaction.guild.get_member(self.app_id)
        if target is None:
            await interaction.response.send_message(
                "⚠️ That app is no longer in the server.", ephemeral=True
            )
            await interaction.message.edit(view=verification_view(self.app_id, disabled=True))
            return
        role = interaction.guild.get_role(BOT_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                f"Error: Could not find the Bot role ({int(BOT_ROLE_ID)}).", ephemeral=True
            )
            return
        try:
            await target.add_roles(role, reason=f"App approved by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I can't give that role — my role is probably below the Bot role.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} approved {target.mention} — assigned the Bot role."
        )
        await interaction.message.edit(view=verification_view(self.app_id, disabled=True))


class DeclineButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"app_verify:decline:(?P<id>[0-9]+)"
):
    def __init__(self, app_id: int):
        super().__init__(
            discord.ui.Button(
                label="Decline",
                style=discord.ButtonStyle.red,
                custom_id=f"app_verify:decline:{app_id}",
            )
        )
        self.app_id = app_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        if await deny_if_not_reviewer(interaction):
            return
        # Nedtrekksmenyen vises bare for den som trykket
        await interaction.response.send_message(
            "Select an action for this app:",
            view=DeclineView(self.app_id, interaction.message),
            ephemeral=True,
        )


class DeclineDropdown(discord.ui.Select):
    def __init__(self, app_id: int, original_message: discord.Message):
        self.app_id = app_id
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
        if await deny_if_not_reviewer(interaction):
            return
        choice = self.values[0]
        target = interaction.guild.get_member(self.app_id)
        name = target.name if target else f"app {self.app_id}"
        reason = f"App declined by {interaction.user}"

        try:
            if choice == "Ban":
                # Ban virker også om appen allerede har forlatt serveren
                await interaction.guild.ban(discord.Object(id=self.app_id), reason=reason)
                result_text = f"🔨 {interaction.user.mention} decided to **Ban** {name}."
            elif choice == "Kick":
                if target is None:
                    await interaction.response.send_message(
                        "⚠️ That app is no longer in the server.", ephemeral=True
                    )
                    return
                await target.kick(reason=reason)
                result_text = f"👢 {interaction.user.mention} decided to **Kick** {name}."
            else:
                result_text = f"⏹️ {interaction.user.mention} chose **No Action** for <@{self.app_id}> (remains restricted)."
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ I don't have permission to do that (check Kick/Ban Members and my role position).",
                ephemeral=True,
            )
            return
        except Exception as e:
            logger.exception("App decline action failed")
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)
            return

        await self.original_message.edit(view=verification_view(self.app_id, disabled=True))
        await interaction.response.send_message("Action completed.", ephemeral=True)
        await interaction.channel.send(result_text)


class DeclineView(discord.ui.View):
    def __init__(self, app_id: int, original_message: discord.Message):
        super().__init__(timeout=60)
        self.add_item(DeclineDropdown(app_id, original_message))


class BotManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Gjør Approve/Decline-knappene aktive igjen etter restart
        self.bot.add_dynamic_items(ApproveButton, DeclineButton)

    async def cog_unload(self):
        self.bot.remove_dynamic_items(ApproveButton, DeclineButton)

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

                await log_channel.send(embed=embed, view=verification_view(member.id))


async def setup(bot):
    await bot.add_cog(BotManager(bot))
