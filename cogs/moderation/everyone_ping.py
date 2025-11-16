import discord
from discord.ext import commands
import json
from pathlib import Path
from datetime import datetime

WARNINGS_FILE = Path("./cogs/moderation/warnings.json")
MOD_CHANNEL_ID = 1435357010500780052
OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090
IMMUNE_ROLE_IDS = [
    OWNER_ROLE_ID,
    ADMIN_ROLE_ID,
]
WARNINGS_FOR_EVERYONE = 2


def load_warnings():
    if WARNINGS_FILE.exists():
        return json.loads(WARNINGS_FILE.read_text())
    return {}


def save_warnings(warnings):
    WARNINGS_FILE.write_text(json.dumps(warnings, indent=4))


def add_warning(user_id: int, reason: str):
    warnings = load_warnings()
    str_id = str(user_id)
    if str_id not in warnings:
        warnings[str_id] = []
    warnings[str_id].append(reason)
    save_warnings(warnings)
    return len(warnings[str_id])


class EveryonePingFilter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Skip immune roles
        if any(role.id in IMMUNE_ROLE_IDS for role in message.author.roles):
            return

        if "@everyone" in message.content or "@here" in message.content:
            try:
                await message.delete()
                reason = "Pinged @everyone/@here"
                total_warnings = 0
                for _ in range(WARNINGS_FOR_EVERYONE):
                    total_warnings = add_warning(message.author.id, reason)

                # Send embed to mod channel
                mod_channel = self.bot.get_channel(MOD_CHANNEL_ID)
                if mod_channel:
                    embed = discord.Embed(
                        title="⚠️ User Warning",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(),
                    )
                    embed.add_field(
                        name="User",
                        value=f"{message.author} ({message.author.id})",
                        inline=False,
                    )
                    embed.add_field(name="Reason", value=reason, inline=False)
                    embed.add_field(
                        name="Total Warnings", value=str(total_warnings), inline=False
                    )
                    embed.set_footer(text="@everyone Ping Filter")
                    await mod_channel.send(embed=embed)

                # Optional: notify user
                await message.channel.send(
                    f"{message.author.mention}, you are not allowed to ping @everyone/@here!",
                    delete_after=5,
                )

            except discord.Forbidden:
                print("⚠️ Missing permission to delete messages!")
            except Exception as e:
                print(f"⚠️ Error handling @everyone ping: {e}")


async def setup(bot):
    await bot.add_cog(EveryonePingFilter(bot))
