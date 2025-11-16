import discord
from discord.ext import commands, tasks
import json
from pathlib import Path
from datetime import datetime, timedelta

# === CONFIG ===
WARNINGS_FILE = Path("./cogs/moderation/warnings.json")
MOD_CHANNEL_ID = 1435357010500780052
OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090
IMMUNE_ROLE_IDS = [
    OWNER_ROLE_ID,
    ADMIN_ROLE_ID,
]


class RepeatWarnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_warnings.start()

    def cog_unload(self):
        self.check_warnings.cancel()

    @tasks.loop(minutes=2)
    async def check_warnings(self):
        """Checks all users' warnings and applies a timeout if necessary."""
        if not WARNINGS_FILE.exists():
            return

        with open(WARNINGS_FILE) as f:
            data = json.load(f)

        for user_id, reasons in data.items():
            if len(reasons) >= 3:
                for guild in self.bot.guilds:
                    member = guild.get_member(int(user_id))
                    if member:
                        # Skip immune roles
                        if any(role.id in IMMUNE_ROLE_IDS for role in member.roles):
                            continue

                        try:
                            # Apply 1-hour timeout
                            await member.timeout(
                                until=datetime.utcnow() + timedelta(hours=1),
                                reason="Reached 3 warnings (auto moderation)",
                            )

                            # Send log message
                            embed = discord.Embed(
                                title="🚫 Automatic Timeout",
                                description=(
                                    f"**User:** {member.mention}\n"
                                    f"**Action:** 1 hour timeout\n"
                                    f"**Reason:** Reached 3 warnings\n"
                                    f"**Total warnings before reset:** {len(reasons)}"
                                ),
                                color=discord.Color.red(),
                                timestamp=datetime.now(),
                            )
                            embed.set_footer(text="Repeat Warning System")

                            mod_channel = self.bot.get_channel(MOD_CHANNEL_ID)
                            if mod_channel:
                                await mod_channel.send(embed=embed)

                            # Reset user's warnings after timeout
                            data[user_id] = []
                            with open(WARNINGS_FILE, "w") as wf:
                                json.dump(data, wf, indent=4)

                        except discord.Forbidden:
                            print(f"⚠️ Missing permission to timeout {member}.")
                        except Exception as e:
                            print(f"⚠️ Error while timing out {member}: {e}")

    @check_warnings.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(RepeatWarnings(bot))
