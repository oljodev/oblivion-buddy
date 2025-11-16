import discord
from discord.ext import commands
import re
import json
from pathlib import Path

# --- KONFIG ---
OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090
ALLOWED_ROLES = [OWNER_ROLE_ID, ADMIN_ROLE_ID]
MOD_CHANNEL_ID = 1435357010500780052
WARNINGS_FILE = Path("./cogs/moderation/warnings.json")

# Regex for å finne Discord invite-lenker
INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord\.com/invite)/\S+"
)


# --- Hjelpefunksjoner ---
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
    return len(warnings[str_id])  # Return antall warnings


# --- Cog ---
class DiscordLinksFilter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorer botter
        if message.author.bot:
            return

        # Sjekk om brukeren har tillatt rolle
        allowed = any(role.id in ALLOWED_ROLES for role in message.author.roles)
        if allowed:
            return

        # Sjekk om meldingen inneholder Discord-invite
        if INVITE_REGEX.search(message.content):
            try:
                await message.delete()
                reason = "Sent a Discord invite link"
                warning_count = add_warning(message.author.id, reason)

                # Send embed til moderator-kanal
                mod_channel = self.bot.get_channel(MOD_CHANNEL_ID)
                if mod_channel:
                    embed = discord.Embed(
                        title="⚠️ User Warning",
                        color=discord.Color.orange(),
                        timestamp=message.created_at,
                    )
                    embed.add_field(
                        name="User",
                        value=f"{message.author} ({message.author.id})",
                        inline=False,
                    )
                    embed.add_field(name="Reason", value=reason, inline=False)
                    embed.add_field(
                        name="Total Warnings", value=str(warning_count), inline=False
                    )
                    embed.set_footer(text="Discord Invite Filter")
                    await mod_channel.send(embed=embed)

                # Valgfritt: kort advarsel til brukeren
                await message.channel.send(
                    f"{message.author.mention}, you are not allowed to send Discord invite links!",
                    delete_after=5,
                )

            except discord.Forbidden:
                print("⚠️ Missing permission to delete messages!")
            except Exception as e:
                print(f"⚠️ Error handling message: {e}")


# --- Setup ---
async def setup(bot):
    await bot.add_cog(DiscordLinksFilter(bot))
