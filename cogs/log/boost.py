import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from channels import LOG_CHANNEL as LOG_CHANNEL_ID


class BoostLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.boost_warning_sent = {}  # Track which boosts we've sent warnings for

    @commands.Cog.listener()
    async def on_ready(self):
        """Start the boost monitoring task when the bot is ready."""
        if not self.check_boost_expiration.is_running():
            self.check_boost_expiration.start()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Listens for member updates and detects when a member boosts the server or removes a boost.
        """
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel is None:
            print(f"Log channel {LOG_CHANNEL_ID} not found!")
            return

        guild = after.guild

        # Check if a new boost was added (the boost count increased)
        if before.premium_since is None and after.premium_since is not None:
            # Member just boosted the server
            try:
                # Get total server boosts
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
                embed.add_field(
                    name="Boost Expires",
                    value=f"<t:{int(after.premium_since.timestamp()) + 2592000}:R>",
                    inline=False,
                )
                embed.set_thumbnail(url=after.display_avatar.url)
                embed.set_footer(text=f"Boosted at: {discord.utils.utcnow()}")

                await log_channel.send(embed=embed)
                print(
                    f"{after.display_name} boosted the server! Total boosts: {total_boosts}"
                )

                # Reset warning tracking for this boost
                self.boost_warning_sent[after.id] = False

            except Exception as e:
                print(f"Error logging boost: {e}")

        # Check if a boost was removed (premium_since is no longer None but now None)
        elif before.premium_since is not None and after.premium_since is None:
            # Member's boost was removed or expired
            try:
                # Get total server boosts
                total_boosts = guild.premium_subscription_count

                # Create embed
                embed = discord.Embed(
                    title="❌ Server Boost Removed",
                    description=f"{after.mention}'s boost has been removed or expired.",
                    color=discord.Color.greyple(),
                )
                embed.add_field(
                    name="Member",
                    value=f"{after.display_name} ({after.id})",
                    inline=False,
                )
                embed.add_field(
                    name="Total Server Boosts", value=str(total_boosts), inline=False
                )
                embed.add_field(
                    name="Was Boosting Since",
                    value=f"<t:{int(before.premium_since.timestamp())}:F>",
                    inline=False,
                )
                embed.set_thumbnail(url=after.display_avatar.url)
                embed.set_footer(text=f"Removed at: {discord.utils.utcnow()}")

                await log_channel.send(embed=embed)
                print(
                    f"{after.display_name}'s boost was removed! Total boosts: {total_boosts}"
                )

                # Clean up warning tracking
                if after.id in self.boost_warning_sent:
                    del self.boost_warning_sent[after.id]

            except Exception as e:
                print(f"Error logging boost removal: {e}")

    @tasks.loop(hours=1)
    async def check_boost_expiration(self):
        """Periodically check for boosts that are about to expire and send warnings."""
        try:
            # Get all guilds the bot is in
            for guild in self.bot.guilds:
                log_channel = guild.get_channel(LOG_CHANNEL_ID)
                if log_channel is None:
                    continue

                # Get all boosting members
                for member in guild.members:
                    if member.premium_since is not None:
                        # Calculate when the boost expires (30 days from premium_since)
                        boost_expiry = member.premium_since + timedelta(days=30)
                        time_until_expiry = boost_expiry - datetime.now(
                            member.premium_since.tzinfo
                        )

                        # Send warning if boost expires in less than 7 days and we haven't sent a warning yet
                        if timedelta(days=0) < time_until_expiry <= timedelta(days=7):
                            if not self.boost_warning_sent.get(member.id, False):
                                # Create warning embed
                                embed = discord.Embed(
                                    title="⏰ Boost Expiration Warning",
                                    description=f"{member.mention}'s server boost will expire soon!",
                                    color=discord.Color.orange(),
                                )
                                embed.add_field(
                                    name="Member",
                                    value=f"{member.display_name} ({member.id})",
                                    inline=False,
                                )
                                embed.add_field(
                                    name="Boost Expires",
                                    value=f"<t:{int(boost_expiry.timestamp())}:R>",
                                    inline=False,
                                )
                                embed.add_field(
                                    name="Time Remaining",
                                    value=f"{time_until_expiry.days} day(s)",
                                    inline=False,
                                )
                                embed.set_thumbnail(url=member.display_avatar.url)
                                embed.set_footer(
                                    text=f"Checked at: {discord.utils.utcnow()}"
                                )

                                await log_channel.send(embed=embed)
                                print(
                                    f"⏰ Boost warning sent for {member.display_name} - expires in {time_until_expiry.days} day(s)"
                                )

                                # Mark that we've sent a warning for this boost
                                self.boost_warning_sent[member.id] = True

        except Exception as e:
            print(f"Error checking boost expiration: {e}")


async def setup(bot):
    await bot.add_cog(BoostLogger(bot))
