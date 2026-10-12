import discord
from discord.ext import commands, tasks
from datetime import datetime
import logging

logger = logging.getLogger("ServerTracker")

from config import Channel
from cogs._shared.json_store import load_json, save_json

STAFF_STATS_CHANNEL_ID = Channel.SIMPLE_STATS
LOG_CHANNEL_ID = Channel.LOG

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
        # Milepæl-listene settes alltid, også hvis fila mangler eller er korrupt
        data = load_json(STATS_FILE, {})
        self.message_count = data.get("message_count", 0)
        self.reaction_count = data.get("reaction_count", 0)
        self.voice_events = data.get("voice_events", 0)
        self.message_to_edit_id = data.get("message_to_edit_id")
        self.announced_message_milestones = data.get("announced_message_milestones", [])
        self.announced_reaction_milestones = data.get("announced_reaction_milestones", [])
        self.announced_voice_milestones = data.get("announced_voice_milestones", [])
        self.announced_member_milestones = data.get("announced_member_milestones", [])
        logger.info(f"✅ Loaded stats from {STATS_FILE}" if data else "No stats file found, starting fresh.")

    def save_stats(self):
        data = {
            "message_count": self.message_count,
            "reaction_count": self.reaction_count,
            "voice_events": self.voice_events,
            "message_to_edit_id": self.message_to_edit_id,
            "announced_message_milestones": self.announced_message_milestones,
            "announced_reaction_milestones": self.announced_reaction_milestones,
            "announced_voice_milestones": self.announced_voice_milestones,
            "announced_member_milestones": self.announced_member_milestones,
        }
        try:
            save_json(STATS_FILE, data, indent=4)
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

    # --- Milestone Helpers ---
    def _get_milestone_every_n(self, current_count, interval):
        """Get the highest milestone reached at every N units (e.g., 10, 20, 30, ...)"""
        if current_count < interval:
            return None
        return (current_count // interval) * interval

    async def _send_milestone_announcement(self, milestone_count, stat_type):
        """Send an embed to the LOG channel announcing a new milestone.

        Args:
            milestone_count: The count that was reached
            stat_type: Type of stat - 'messages', 'reactions', 'voice', or 'members'
        """
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if not channel:
            logger.warning(f"LOG channel {LOG_CHANNEL_ID} not found")
            return

        # Customize the embed based on stat type
        if stat_type == "messages":
            title = "🎉 Message Milestone Reached!"
            description = (
                f"The discord server has reached **{milestone_count:,}** messages!"
            )
        elif stat_type == "reactions":
            title = "🎉 Reaction Milestone Reached!"
            description = (
                f"The discord server has reached **{milestone_count:,}** reactions!"
            )
        elif stat_type == "voice":
            title = "🎉 Voice Channel Milestone Reached!"
            description = f"The discord server has reached **{milestone_count:,}** voice channel joins/leaves!"
        elif stat_type == "members":
            title = "🎉 Member Milestone Reached!"
            description = (
                f"The discord server has reached **{milestone_count:,}** members!"
            )

        embed = discord.Embed(
            title=title,
            description=description,
            colour=discord.Colour.gold(),
            timestamp=datetime.now(),
        )
        embed.set_footer(text="Oblivion Buddy Milestone Tracker")

        try:
            await channel.send(embed=embed)
            logger.info(
                f"Milestone announcement sent for {stat_type}: {milestone_count}"
            )
        except Exception:
            logger.exception(
                f"Failed to send milestone announcement for {stat_type}: {milestone_count}"
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

        # Check for message milestone (every 1000)
        message_milestone = self._get_milestone_every_n(self.message_count, 1000)
        if (
            message_milestone
            and message_milestone not in self.announced_message_milestones
        ):
            await self._send_milestone_announcement(message_milestone, "messages")
            self.announced_message_milestones.append(message_milestone)
            self.save_stats()

        # Check for reaction milestone (every 100)
        reaction_milestone = self._get_milestone_every_n(self.reaction_count, 100)
        if (
            reaction_milestone
            and reaction_milestone not in self.announced_reaction_milestones
        ):
            await self._send_milestone_announcement(reaction_milestone, "reactions")
            self.announced_reaction_milestones.append(reaction_milestone)
            self.save_stats()

        # Check for voice milestone (every 100)
        voice_milestone = self._get_milestone_every_n(self.voice_events, 100)
        if voice_milestone and voice_milestone not in self.announced_voice_milestones:
            await self._send_milestone_announcement(voice_milestone, "voice")
            self.announced_voice_milestones.append(voice_milestone)
            self.save_stats()

        # Check for member milestone (every 10)
        member_milestone = self._get_milestone_every_n(total_members, 10)
        if (
            member_milestone
            and member_milestone not in self.announced_member_milestones
        ):
            await self._send_milestone_announcement(member_milestone, "members")
            self.announced_member_milestones.append(member_milestone)
            self.save_stats()

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
        embed.add_field(name="👥 Members", value=f"{total_members - 3:,}", inline=True)
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
