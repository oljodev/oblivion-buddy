import discord
from discord.ext import commands, tasks
from aiomcrcon import Client
import os
import re
from datetime import datetime

RCON_IP = os.getenv("RCON_IP", "localhost")
RCON_PORT = int(os.getenv("RCON_PORT", 25575))
RCON_PASS = os.getenv("RCON_PASS", "secret")

LOG_CHANNEL_ID = 1452598796377653331
STATUS_CHANNEL_ID = 1422934996976402442
SERVER_NAME = "Oblivion SMP"

# Keywords that should be filtered out from the player list
FILTER_WORDS = {
    "there",
    "are",
    "of",
    "a",
    "max",
    "players",
    "online",
    "server",
    "info",
    "list",
    "connected",
    "status",
    "currently",
    "player",
    "available",
}


class ServerStatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_message = None
        self.last_status = None
        self.log_message = None
        self.last_player_count = 0
        self.last_logged_threshold = 0
        self.log_message_sent_time = None
        self.update_status.start()

    def cog_unload(self):
        self.update_status.cancel()

    @tasks.loop(seconds=60)
    async def update_status(self):
        await self.bot.wait_until_ready()

        channel = self.bot.get_channel(STATUS_CHANNEL_ID)
        if not channel:
            print("⚠️ Could not find the status channel.")
            return

        # --- PRØV Å HENTE SERVERDATA ---
        try:
            async with Client(RCON_IP, RCON_PORT, RCON_PASS) as client:
                response = await client.send_cmd("list")
                is_online = True
        except Exception:
            response = None
            is_online = False

        # --- PARSE SPILLERDATA ---
        player_names = []
        player_count = 0
        max_players = 0

        if is_online and response:
            try:
                text = response[0] if isinstance(response, tuple) else response

                # Use regex to isolate the section containing the count and the names
                # This helps skip multi-line or non-standard prefix data

                # 1. EXTRACT NUMBERS (Current & Max)
                # Look for the standard phrase "X of a max of Y players"
                count_match = re.search(
                    r"(\d+)\s+of\s+a\s+max\s+of\s+(\d+)", text, re.IGNORECASE
                )

                if count_match:
                    player_count = int(count_match.group(1))
                    max_players = int(count_match.group(2))

                # Fallback: find any two numbers, usually "X/Y" or "X out of Y"
                elif not count_match:
                    numbers = re.findall(r"\d+", text)
                    if len(numbers) >= 2:
                        # We can't be sure which is which, but this is a reasonable guess for fallback
                        player_count = int(numbers[0])
                        max_players = int(numbers[1])

                # 2. EXTRACT NAMES
                # Find the names list, which always follows "online:" or just ends the string

                # Try to capture the list after "online:"
                names_match = re.search(r"online:?\s*(.*)", text, re.IGNORECASE)

                raw_names_str = ""
                if names_match:
                    # Captures everything after "online:"
                    raw_names_str = names_match.group(1).strip()
                else:
                    # If "online:" wasn't found (e.g., 0 players), use the whole string as a fallback
                    # and rely on the filter below to clean it.
                    raw_names_str = text.strip()

                # Clean and filter tokens
                tokens = re.split(r"[,\s\n]+", raw_names_str)
                cleaned_names = []
                for t in tokens:
                    clean_t = re.sub(r"[^A-Za-z0-9_]+", "", t).strip()
                    if (
                        3
                        <= len(clean_t)
                        <= 16  # Valid name length check (3-16 standard)
                        and clean_t.lower() not in FILTER_WORDS  # Exclude common words
                        and not re.search(
                            r"^\d+$", clean_t
                        )  # Exclude pure numbers/timestamps
                        and clean_t.lower() != SERVER_NAME.lower()
                    ):  # Exclude the server name itself
                        cleaned_names.append(clean_t)

                # Keep only unique names
                player_names = sorted(list(set(cleaned_names)), key=str.lower)

            except Exception as e:
                print(f"Error parsing status: {e}")
                player_names = []
                player_count = 0

        # --- LAG EMBED ---
        color = discord.Color.green() if is_online else discord.Color.red()
        icon = "🟢" if is_online else "🔴"
        status_text = "Online" if is_online else "Offline"

        embed = discord.Embed(
            title=f"{icon} {SERVER_NAME} Status",
            color=color,
            timestamp=datetime.now(),
        )

        embed.add_field(name="📡 Status", value=status_text, inline=True)
        embed.add_field(name="🌐 IP", value=f"`{RCON_IP}`", inline=True)

        embed.add_field(
            name="👥 Players",
            value=f"{player_count}/{max_players}" if is_online else "0/0",
            inline=True,
        )

        if is_online and player_count >= 5:
            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                # Calculate the current threshold (5, 10, 15, 20, etc.)
                current_threshold = (player_count // 5) * 5

                # Check if we've crossed a threshold
                should_send_new = False

                # If player count dropped below the last logged threshold, reset
                if player_count < self.last_logged_threshold:
                    self.last_logged_threshold = 0
                    should_send_new = False

                # If we've reached a new threshold, send/edit
                if current_threshold > self.last_logged_threshold:
                    self.last_logged_threshold = current_threshold
                    should_send_new = True

                # Update log message if threshold reached
                if should_send_new or self.log_message is None:
                    player_list_str = (
                        "\n".join(player_names)
                        if player_names
                        else "No players online."
                    )
                    current_time = datetime.now()
                    log_embed = discord.Embed(
                        title="Server Population Alert",
                        description=f"There are currently **{player_count}** players online:\n{player_list_str}",
                        color=discord.Color.blue(),
                        timestamp=current_time,
                    )
                    log_embed.set_footer(
                        text=f"Sent: {current_time.strftime('%H:%M:%S')} | Last updated: {current_time.strftime('%H:%M:%S')}"
                    )

                    if should_send_new and self.log_message is None:
                        # Send a new message
                        try:
                            self.log_message = await log_channel.send(embed=log_embed)
                            self.log_message_sent_time = current_time
                        except Exception as e:
                            print(f"Error sending log message: {e}")
                    elif self.log_message:
                        # Edit existing message
                        try:
                            log_embed.set_footer(
                                text=f"Sent: {self.log_message_sent_time.strftime('%H:%M:%S')} | Last generated: {current_time.strftime('%H:%M:%S')}"
                            )
                            await self.log_message.edit(embed=log_embed)
                        except discord.NotFound:
                            # Message was deleted, send a new one
                            try:
                                self.log_message = await log_channel.send(
                                    embed=log_embed
                                )
                                self.log_message_sent_time = current_time
                            except Exception as e:
                                print(
                                    f"Error sending new log message after deletion: {e}"
                                )
                        except Exception as e:
                            print(f"Error editing log message: {e}")
                elif self.log_message:
                    # Update footer with last generated time
                    try:
                        current_time = datetime.now()
                        if self.log_message.embeds:
                            log_embed = self.log_message.embeds[0]
                            log_embed.set_footer(
                                text=f"Sent: {self.log_message_sent_time.strftime('%H:%M:%S')} | Last generated: {current_time.strftime('%H:%M:%S')}"
                            )
                            await self.log_message.edit(embed=log_embed)
                    except Exception as e:
                        print(f"Error updating log message footer: {e}")

        if is_online:
            if player_names:
                display_names = player_names[:20]
                names_str = "\n".join(display_names)
                if len(player_names) > 20:
                    names_str += f"\n...and {len(player_names) - 20} more"

                embed.add_field(
                    name="🧍 Player List:",
                    value=names_str,
                    inline=False,
                )
            else:
                embed.add_field(
                    name="🧍 Player List:", value="*No players online.*", inline=False
                )
        else:
            embed.add_field(
                name="🧍 Player List:", value="*Server is offline.*", inline=False
            )

        embed.set_footer(
            text=f"Sent: {datetime.now().strftime('%H:%M:%S')} | Last updated: {datetime.now().strftime('%H:%M:%S')}"
        )

        # --- SEND ELLER OPPDATER MELDING ---
        if not self.status_message:
            async for msg in channel.history(limit=10):
                if msg.author == self.bot.user and msg.embeds:
                    self.status_message = msg
                    break

        if self.status_message:
            try:
                await self.status_message.edit(embed=embed)
            except discord.NotFound:
                self.status_message = await channel.send(embed=embed)
        else:
            self.status_message = await channel.send(embed=embed)

        # --- OPPDATER BOT STATUS (ACTIVITY) ---
        if is_online:
            activity_name = f"{SERVER_NAME} with {player_count} players"
            activity = discord.Game(name=activity_name)
            await self.bot.change_presence(activity=activity)
        else:
            activity = discord.CustomActivity(name="Server Offline")
            await self.bot.change_presence(
                status=discord.Status.idle, activity=activity
            )

    @update_status.before_loop
    async def before_update_status(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ServerStatusCog(bot))
