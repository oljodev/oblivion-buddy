import discord
from discord.ext import commands
from pathlib import Path
from datetime import datetime
import json
import re

# === CONFIG ===
BAD_WORDS_FILE = Path(".cogs/moderation/bad_words.txt")  # Din ordliste
WARNINGS_FILE = Path(".cogs/moderation/warnings.json")
MOD_CHANNEL_ID = 1435357010500780052
OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090
IMMUNE_ROLE_IDS = [
    OWNER_ROLE_ID,
    ADMIN_ROLE_ID,
]

# Last ordlisten
if BAD_WORDS_FILE.exists():
    with open(BAD_WORDS_FILE, encoding="utf-8") as f:
        BAD_WORDS = [line.strip().lower() for line in f if line.strip()]
else:
    BAD_WORDS = []


# --- Warnings system ---
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


# --- Cog ---
class BadWordsFilter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Skip immune roles
        if any(role.id in IMMUNE_ROLE_IDS for role in message.author.roles):
            return

        content = message.content.lower()

        # Sjekk mot ordlisten med regex for hele ord
        for word in BAD_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", content):
                try:
                    await message.delete()
                    reason = f"Used prohibited word: '{word}'"
                    count = add_warning(message.author.id, reason)

                    # Embed til mod-kanal
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
                            name="Total Warnings", value=str(count), inline=False
                        )
                        embed.set_footer(text="Bad Words Filter")
                        await mod_channel.send(embed=embed)

                    # Kort advarsel til brukeren
                    await message.channel.send(
                        f"{message.author.mention}, your message contained prohibited words!",
                        delete_after=5,
                    )

                except discord.Forbidden:
                    print("⚠️ Missing permission to delete message.")
                except Exception as e:
                    print(f"⚠️ Error in bad words filter: {e}")
                break  # Stop etter første treff


# --- Setup ---
async def setup(bot):
    await bot.add_cog(BadWordsFilter(bot))
