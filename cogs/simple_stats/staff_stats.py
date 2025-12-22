import discord
from discord.ext import commands, tasks
from datetime import datetime
import logging
import json
import os

logger = logging.getLogger("ServerTracker")

STAFF_STATS_CHANNEL_ID = 1433549179942338570

STATS_FILE = "./cogs/simple_stats/staff_stats.json"


class ServerTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.embed_channel_id = STAFF_STATS_CHANNEL_ID

        # Default stats
        self.message_count = 0
        self.reaction_count = 0
        self.voice_events = 0
        self.message_to_edit_id = None

        # Load stats from file if exists
        self.load_stats()

        # Start embed updater
        self.update_embed.start()
        logger.info("📊 ServerTracker cog initialized")

    # --- Persistence ---
    def load_stats(self):
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, "r") as f:
                    data = json.load(f)
                    self.message_count = data.get("message_count", 0)
                    self.reaction_count = data.get("reaction_count", 0)
                    self.voice_events = data.get("voice_events", 0)
                    self.message_to_edit_id = data.get("message_to_edit_id")
                    logger.info(f"✅ Loaded stats from {STATS_FILE}")
            except Exception as e:
                logger.error(f"Failed to load stats: {e}")
        else:
            logger.info("No stats file found, starting fresh.")

    def save_stats(self):
        data = {
            "message_count": self.message_count,
            "reaction_count": self.reaction_count,
            "voice_events": self.voice_events,
            "message_to_edit_id": self.message_to_edit_id,
        }
        try:
            with open(STATS_FILE, "w") as f:
                json.dump(data, f, indent=4)
            logger.debug("Stats saved to JSON")
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

    # --- Event Listeners ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        self.message_count += 1
        self.save_stats()
        logger.debug(f"Message from {message.author}: {message.content[:50]}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return
        self.reaction_count += 1
        self.save_stats()
        logger.debug(f"Reaction added by {user}: {reaction.emoji}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel != after.channel:
            self.voice_events += 1
            self.save_stats()
            logger.debug(
                f"Voice state change for {member}: {before.channel} -> {after.channel}"
            )

    # --- Embed Updater ---
    @tasks.loop(seconds=60)
    async def update_embed(self):
        if not self.embed_channel_id:
            logger.warning("No embed_channel_id set! Please configure it in the code.")
            return

        channel = self.bot.get_channel(self.embed_channel_id)
        if not channel:
            logger.error(f"Could not find channel with ID {self.embed_channel_id}")
            return

        guild = channel.guild
        total_members = guild.member_count

        embed = discord.Embed(
            title=f"📊 Live Server Statistics – {guild.name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(),
        )
        embed.add_field(
            name="💬 Messages Sent", value=f"{self.message_count:,}", inline=True
        )
        embed.add_field(
            name="😊 Reactions Used", value=f"{self.reaction_count:,}", inline=True
        )
        embed.add_field(
            name="🎙️ Voice Channel Joins/Leaves",
            value=f"{self.voice_events:,}",
            inline=True,
        )
        embed.add_field(name="👥 Members", value=f"{total_members:,}", inline=True)
        embed.set_footer(text="Auto-updated every 60 seconds")

        try:
            # Check if we have a previous embed to edit
            msg = None
            if self.message_to_edit_id:
                try:
                    msg = await channel.fetch_message(self.message_to_edit_id)
                except discord.NotFound:
                    logger.warning(
                        "Previous stats embed not found, creating a new one."
                    )
                    self.message_to_edit_id = None

            if not msg:
                # Delete old embeds in channel to avoid duplicates
                async for m in channel.history(limit=50):
                    if m.author == self.bot.user and m.embeds:
                        await m.delete()
                        logger.info("Deleted old stats embed")

                msg = await channel.send(embed=embed)
                self.message_to_edit_id = msg.id
                self.save_stats()
                logger.info(f"📢 Created new stats embed in #{channel.name}")
            else:
                await msg.edit(embed=embed)
                logger.debug("Embed updated successfully")

        except Exception as e:
            logger.error(f"Failed to update embed: {e}")

    @update_embed.before_loop
    async def before_update_embed(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ServerTracker(bot))
