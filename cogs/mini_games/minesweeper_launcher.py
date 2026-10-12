import logging

import discord
from discord import app_commands, ui
from discord.ext import commands

from config import GUILD_ID, MINESWEEPER_APP_ID, Channel

logger = logging.getLogger("Minesweeper")

APPLICATION_ID = MINESWEEPER_APP_ID
VOICE_CHANNEL_ID = Channel.GENERAL_VOICE
EMBED_COLOR = 0xFFCC00


class MinesweeperLauncher(commands.Cog):
    """Launcher for the Oblivion Minesweeper Discord Activity."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="minesweeper",
        description="Launch Oblivion Minesweeper — a Discord Activity mini-game.",
    )
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def minesweeper(self, interaction: discord.Interaction):
        """Create an Activity invite for the mini-games voice channel and reply with a launch button."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            channel = self.bot.get_channel(VOICE_CHANNEL_ID)
            if channel is None:
                channel = await self.bot.fetch_channel(VOICE_CHANNEL_ID)

            invite = await channel.create_invite(
                max_age=86400,
                target_type=discord.InviteTarget.embedded_application,
                target_application_id=APPLICATION_ID,
                reason="Minesweeper Activity launcher",
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                f"Could not create Activity invite:\n```\n{type(exc).__name__}: {exc}\n```",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Oblivion Minesweeper",
            description=(
                f"Click **Play Minesweeper** to drop into {channel.mention} "
                "and launch the Activity."
            ),
            color=EMBED_COLOR,
        )
        embed.set_footer(text="Oblivion SMP • Mini-Games")

        view = ui.View()
        view.add_item(
            ui.Button(
                label="Play Minesweeper",
                style=discord.ButtonStyle.link,
                url=invite.url,
                emoji="💣",
            )
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    if not APPLICATION_ID:
        logger.info("minesweeper_app_id is 0 — /minesweeper disabled.")
        return
    await bot.add_cog(MinesweeperLauncher(bot))
