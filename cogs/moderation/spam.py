import discord
from discord.ext import commands
import json
from pathlib import Path
from datetime import datetime

WARNINGS_FILE = Path("./cogs/moderation/warnings.json")
MOD_CHANNEL_ID = 1435357010500780052

message_log = {}


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


class SpamFilter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        user_id = message.author.id
        now = message.created_at.timestamp()

        # Legg til melding i logg
        if user_id not in message_log:
            message_log[user_id] = []
        message_log[user_id].append(now)

        # Fjern gamle meldinger (mer enn 10 sekunder)
        message_log[user_id] = [t for t in message_log[user_id] if now - t < 10]

        if len(message_log[user_id]) > 5:
            try:
                await message.delete()
                reason = "Spamming messages"
                count = add_warning(user_id, reason)

                embed = discord.Embed(
                    title="⚠️ User Warning - Spam Detected",
                    color=discord.Color.orange(),
                    timestamp=datetime.now(),
                )
                embed.add_field(
                    name="User", value=f"{message.author} ({user_id})", inline=False
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Total Warnings", value=str(count), inline=False)

                mod_channel = self.bot.get_channel(MOD_CHANNEL_ID)
                if mod_channel:
                    await mod_channel.send(embed=embed)

                await message.channel.send(
                    f"{message.author.mention}, stop spamming!", delete_after=5
                )

                message_log[user_id] = []  # Reset brukerens logg

            except Exception as e:
                print(f"⚠️ Spam filter error: {e}")


async def setup(bot):
    await bot.add_cog(SpamFilter(bot))
