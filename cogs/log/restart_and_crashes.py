import os
import logging
from aiomcrcon import Client
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

LOG_CHANNEL_ID = 1452598796377653331

RCON_IP = os.getenv("RCON_IP", "localhost")
RCON_PORT = int(os.getenv("RCON_PORT", 25575))
RCON_PASS = os.getenv("RCON_PASS", "secret")

logger = logging.getLogger(__name__)


class RestartAndCrashLogger(commands.Cog):
    """Cog that monitors Minecraft server status and logs restarts/crashes to Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.server_was_online = False
        self.check_server_status.start()

    def cog_unload(self):
        """Cancel the background task when the cog is unloaded."""
        self.check_server_status.cancel()

    async def check_rcon_connection(self) -> bool:
        """
        Try to connect to the Minecraft server via RCON.
        Returns True if connection successful, False otherwise.
        """
        try:
            async with Client(RCON_IP, RCON_PORT, passwd=RCON_PASS) as client:
                # Send a simple command to verify connection
                response = await client.send_cmd("list")
                return response is not None
        except Exception as e:
            logger.debug(f"RCON connection failed: {e}")
            return False

    async def send_crash_embed(self, log_channel: discord.TextChannel):
        """Send an embed message indicating the server has crashed."""
        embed = discord.Embed(
            title="💥 Minecraft Server Crashed!",
            description="The Minecraft server has crashed and is no longer responding to RCON commands.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Server",
            value=f"{RCON_IP}:{RCON_PORT}",
            inline=False,
        )
        embed.add_field(
            name="Status",
            value="⛔ Offline",
            inline=False,
        )
        embed.set_footer(text="Monitoring status...")

        try:
            await log_channel.send(embed=embed)
            logger.info("Crash event logged to Discord")
        except Exception as e:
            logger.error(f"Failed to send crash embed: {e}")

    async def send_restart_embed(self, log_channel: discord.TextChannel):
        """Send an embed message indicating the server has restarted."""
        embed = discord.Embed(
            title="🔄 Minecraft Server Restarted!",
            description="The Minecraft server has restarted and is back online.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Server",
            value=f"{RCON_IP}:{RCON_PORT}",
            inline=False,
        )
        embed.add_field(
            name="Status",
            value="✅ Online",
            inline=False,
        )
        embed.set_footer(text="Server is ready for players!")

        try:
            await log_channel.send(embed=embed)
            logger.info("Restart event logged to Discord")
        except Exception as e:
            logger.error(f"Failed to send restart embed: {e}")

    @tasks.loop(seconds=30)
    async def check_server_status(self):
        """
        Periodically check the Minecraft server status via RCON.
        Detect restarts and crashes.
        """
        try:
            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel is None:
                logger.warning(f"Log channel {LOG_CHANNEL_ID} not found!")
                return

            # Check if server is online
            server_is_online = await self.check_rcon_connection()

            # Server came back online (was offline, now online = RESTART)
            if not self.server_was_online and server_is_online:
                logger.info("🔄 Server restart detected!")
                await self.send_restart_embed(log_channel)
                self.server_was_online = True

            # Server went offline (was online, now offline = CRASH)
            elif self.server_was_online and not server_is_online:
                logger.info("💥 Server crash detected!")
                await self.send_crash_embed(log_channel)
                self.server_was_online = False

        except Exception as e:
            logger.error(f"Error checking server status: {e}")

    @check_server_status.before_loop
    async def before_check_server_status(self):
        """Wait for the bot to be ready before starting the status check."""
        await self.bot.wait_until_ready()
        # Initial check to set the baseline state
        self.server_was_online = await self.check_rcon_connection()
        logger.info(
            f"Initial server state: {'Online' if self.server_was_online else 'Offline'}"
        )


async def setup(bot: commands.Bot):
    """Load the cog into the bot."""
    await bot.add_cog(RestartAndCrashLogger(bot))
