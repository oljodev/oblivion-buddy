import discord
from discord.ext import commands
import aiomcrcon
import json
import os

DISCORD_TO_MC_CHANNEL_ID = 1442939418821529600
RCON_IP = os.getenv("RCON_IP", "localhost")
RCON_PORT = os.getenv("RCON_PORT", 25575)
RCON_PASS = os.getenv("RCON_PASS", "secret")


class DiscordToMinecraft(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorer botten & DMs
        if message.author.bot or message.guild is None:
            return

        # Sjekk at det er riktig kanal
        if message.channel.id != DISCORD_TO_MC_CHANNEL_ID:
            return

        # Format Minecraft tellraw melding
        mc_username = message.author.name
        content = message.content.replace('"', "'")  # tellraw hater doble anførselstegn

        tellraw_json = [
            {"text": "[DISCORD] ", "color": "blue"},
            {"text": f"{mc_username}: ", "color": "white"},
            {"text": content, "color": "white"},
        ]

        tellraw_command = f"tellraw @a {json.dumps(tellraw_json)}"

        # Send til Minecraft via RCON
        try:
            async with aiomcrcon.Client(RCON_IP, RCON_PORT, RCON_PASS) as client:
                await client.send_cmd(tellraw_command)

        except Exception as e:
            print(f"[DiscordToMinecraft] Failed to send message: {e}")


async def setup(bot):
    await bot.add_cog(DiscordToMinecraft(bot))
