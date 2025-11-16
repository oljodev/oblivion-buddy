import discord
from discord.ext import commands, tasks
from aiomcrcon import Client
import getenv
from datetime import datetime

RCON_IP = getenv.get("RCON_IP", "localhost")
RCON_PORT = getenv.get("RCON_PORT", 25575)
RCON_PASS = getenv.get("RCON_PASS", "secret")

STATUS_CHANNEL_ID = 1422934996976402442
SERVER_NAME = "Oblivion SMP"

status_message = None


class ServerStatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_message = None
        self.last_status = None
        self.update_status.start()

    def cog_unload(self):
        self.update_status.cancel()

    @tasks.loop(seconds=30)
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
                # Eksempelrespons: "There are 1 of a max of 20 players online: username"
                text = response[0] if isinstance(response, tuple) else response
                parts = text.split(":")
                if len(parts) > 1:
                    player_names = [p.strip() for p in parts[1].split(",") if p.strip()]
                if "There are" in text and "of a max of" in text:
                    player_count = int(text.split("There are ")[1].split(" of")[0])
                    max_players = int(text.split("of a max of ")[1].split(" ")[0])
            except Exception:
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

        if is_online:
            if player_names:
                embed.add_field(
                    name="🧍 Player List",
                    value="\n".join(player_names[:20]),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="🧍 Player List", value="*No players online.*", inline=False
                )
        else:
            embed.add_field(
                name="🧍 Player List", value="*Server is offline.*", inline=False
            )

        embed.set_footer(text="Last updated")

        # --- SEND ELLER OPPDATER MELDING ---
        if not self.status_message:
            async for msg in channel.history(limit=10):
                if msg.author == self.bot.user and msg.embeds:
                    self.status_message = msg
                    break

        if self.status_message:
            await self.status_message.edit(embed=embed)
        else:
            self.status_message = await channel.send(embed=embed)

        # --- OPPDATER KANALNAVN ---
        new_name = f"{icon}│{status_text.lower()}"
        if channel.name != new_name:
            try:
                await channel.edit(name=new_name)
                self.last_status = new_name
                print(f"✅ Updated channel name to {new_name}")
            except discord.Forbidden:
                print("⚠️ Missing permission to change channel name.")
            except Exception as e:
                print(f"⚠️ Error changing channel name: {e}")

    @update_status.before_loop
    async def before_update_status(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ServerStatusCog(bot))
