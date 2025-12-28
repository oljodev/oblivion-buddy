import discord
from discord.ext import commands

LOG_CHANNEL_ID = 1452598796377653331


class BoostLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Listens for member updates and detects when a member boosts the server.
        """
        # Check if a new boost was added (the boost count increased)
        if before.premium_since is None and after.premium_since is not None:
            # Member just boosted the server
            try:
                log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
                if log_channel is None:
                    print(f"Log channel {LOG_CHANNEL_ID} not found!")
                    return

                # Get total server boosts
                guild = after.guild
                total_boosts = guild.premium_subscription_count

                # Create embed
                embed = discord.Embed(
                    title="🚀 Server Boosted!",
                    description=f"{after.mention} just boosted the server!",
                    color=discord.Color.pink(),
                )
                embed.add_field(
                    name="Member",
                    value=f"{after.display_name} ({after.id})",
                    inline=False,
                )
                embed.add_field(
                    name="Total Server Boosts", value=str(total_boosts), inline=False
                )
                embed.set_thumbnail(url=after.display_avatar.url)
                embed.set_footer(text=f"Boosted at: {discord.utils.utcnow()}")

                await log_channel.send(embed=embed)
                print(
                    f"{after.display_name} boosted the server! Total boosts: {total_boosts}"
                )

            except Exception as e:
                print(f"Error logging boost: {e}")


async def setup(bot):
    await bot.add_cog(BoostLogger(bot))
