import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from discord.ui import View, Button, Modal, TextInput
import logging

logger = logging.getLogger("Polls")

GUILD_ID = discord.Object(id=1422932147550818507)

OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090


# ------------------------- Modal for creating poll -------------------------
class PollModal(Modal):
    def __init__(self, poll_cog, creator: discord.User):
        super().__init__(title="Create a Poll")
        self.poll_cog = poll_cog
        self.creator = creator

        self.question = TextInput(
            label="Poll Question",
            placeholder="Enter your question",
            required=True,
            max_length=200,
        )
        self.description = TextInput(
            label="Poll description",
            placeholder="Enter a brief description",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500,
        )
        self.duration = TextInput(
            label="Duration",
            placeholder="Duration (e.g., 10m, 1h, 1d, 45s)",
            required=True,
            max_length=10,
        )

        self.add_item(self.question)
        self.add_item(self.description)
        self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction):
        dur_text = self.duration.value.strip().lower()
        seconds = 0

        if "d" in dur_text:
            seconds += int(dur_text.replace("d", "")) * 86400
        elif "h" in dur_text:
            seconds += int(dur_text.replace("h", "")) * 3600
        elif "m" in dur_text:
            seconds += int(dur_text.replace("m", "")) * 60
        elif "s" in dur_text:
            seconds += int(dur_text.replace("s", "")) * 1
        else:
            await interaction.response.send_message(
                "Invalid duration! Use e.g. `1d`, `1h`, `30m`, `45s`.", ephemeral=True
            )
            return

        end_time = datetime.utcnow() + timedelta(seconds=seconds)

        question = self.question.value.strip()
        description = self.description.value.strip()

        embed = discord.Embed(
            title=f"{question}",
            description=description or "No description provided.",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="Ends",
            value=f"in {dur_text} (<t:{int(end_time.timestamp())}:f>)",
            inline=False,
        )
        embed.add_field(name="Votes", value="0", inline=True)
        embed.add_field(name="Hosted by", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"Today at {datetime.utcnow().strftime('%H:%M UTC')}")

        view = PollView(
            self.poll_cog, end_time, interaction.user, question, description
        )

        # Send ephemeral response first
        await interaction.response.send_message("✅ Poll created!", ephemeral=True)

        # Send poll embed to channel once and store it on the view
        poll_message = await interaction.channel.send(embed=embed, view=view)
        view.message = poll_message

        await self.poll_cog.create_poll_thread(poll_message, question)

        logger.info(f"Poll created by {self.creator}: {question}")


# ------------------------- Modal for text answer -------------------------
class TextResponseModal(Modal):
    def __init__(
        self,
        poll_cog,
        question: str,
        responder: discord.User,
        poll_message: discord.Message,
    ):
        super().__init__(title="Submit Your Answer")
        self.poll_cog = poll_cog
        self.question = question
        self.responder = responder
        self.poll_message = poll_message

        self.response = TextInput(
            label="Title",
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
        )
        self.description = TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500,
        )
        self.add_item(self.response)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        answer = self.response.value.strip()
        description = self.description.value.strip()
        await self.poll_cog.send_response_to_poll_thread(
            self.responder,
            self.question,
            f"\n\n**{answer}\n**{description}",
            self.poll_message,
        )
        await interaction.response.send_message(
            "✅ Your answer has been submitted!", ephemeral=True
        )
        logger.info(f"{self.responder} submitted text answer")


# ------------------------- View for poll -------------------------
class PollView(View):
    def __init__(
        self,
        poll_cog,
        end_time,
        creator: discord.User,
        question: str,
        description: str = "",
    ):
        super().__init__(timeout=None)
        self.poll_cog = poll_cog
        self.creator = creator
        self.question = question
        self.description = description
        self.end_time = end_time
        self.update_task = self.update_countdown.start()

        # Keep reference to the message this view is attached to
        self.message = None

        text_button = Button(label="📝 Send Answer", style=discord.ButtonStyle.primary)
        text_button.callback = self.text_answer
        self.add_item(text_button)

        self.votes = {}

    async def text_answer(self, interaction: discord.Interaction):
        poll_message = interaction.message
        modal = TextResponseModal(
            self.poll_cog, self.question, interaction.user, poll_message
        )
        await interaction.response.send_modal(modal)

    def disable_all_buttons(self):
        for item in self.children:
            item.disabled = True

    @tasks.loop(seconds=1)
    async def update_countdown(self):
        # Update embed every second
        now = datetime.utcnow()
        remaining = self.end_time - now

        if remaining.total_seconds() <= 1:
            self.update_task.cancel()
            self.ended = True
            self.disable_all_buttons()

            # ⚙️ Updated embed (gray and ended)
            ended_embed = discord.Embed(
                title=f"**{self.question}**",
                description="This poll has ended.",
                color=discord.Color.from_rgb(128, 128, 128),
            )
            ended_embed.add_field(
                name="Ended",
                value=f"<t:{int(self.end_time.timestamp())}:f>",
                inline=False,
            )
            # Use poll_cog.poll_votes instead of self.votes length
            votes_count = 0
            if self.message:
                votes_count = self.poll_cog.poll_votes.get(self.message.id, 0)
            ended_embed.add_field(name="Votes", value=str(votes_count), inline=True)
            ended_embed.add_field(
                name="Hosted by", value=self.creator.mention, inline=True
            )
            ended_embed.set_footer(text="Poll Ended")

            try:
                if self.message:
                    await self.message.edit(embed=ended_embed, view=self)
            except Exception as e:
                logger.error(f"⚠️ Failed to edit message: {e}")
            return

        if self.message:
            try:
                embed = self.message.embeds[0]
                embed.set_field_at(
                    0,
                    name="Ends",
                    value=f"in {str(remaining).split('.')[0]}",
                    inline=False,
                )
                # update votes from poll_cog.poll_votes
                votes_count = self.poll_cog.poll_votes.get(self.message.id, 0)
                embed.set_field_at(1, name="Votes", value=str(votes_count), inline=True)
                await self.message.edit(embed=embed, view=self)
            except Exception as e:
                logger.error(f"⚠️ Failed to update countdown: {e}")

    async def on_timeout(self):
        self.disable_all_buttons()
        if hasattr(self, "message"):
            await self.message.edit(view=self)


# ------------------------- Polls Cog -------------------------
class Polls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.poll_threads = {}
        # track votes per poll message id
        self.poll_votes = {}
        logger.info("Polls Cog initialized")

    @app_commands.command(name="poll", description="Create a new poll")
    @app_commands.guilds(GUILD_ID)
    async def poll(self, interaction: discord.Interaction):
        allowed_roles = [
            OWNER_ROLE_ID,
            ADMIN_ROLE_ID,
        ]

        if not any(role.id in allowed_roles for role in interaction.user.roles):
            await interaction.response.send_message(
                "🚫 You don't have permission to start polls.", ephemeral=True
            )
            return

        modal = PollModal(self, interaction.user)
        await interaction.response.send_modal(modal)

    async def create_poll_thread(self, poll_message: discord.Message, question: str):
        """Create a private thread for text answers visible only to OWNER/ADMIN"""
        channel = poll_message.channel
        guild = poll_message.guild

        # Lag privat thread fra kanalen
        thread = await channel.create_thread(
            name=f"Poll Answers - {question}",
            auto_archive_duration=1440,
            type=discord.ChannelType.private_thread,
        )

        # Ping owner/admin i første melding
        mentions = []
        for role_id in [OWNER_ROLE_ID, ADMIN_ROLE_ID]:
            role = guild.get_role(role_id)
            if role:
                mentions.append(role.mention)

        if mentions:
            await thread.send(
                f"⚠️ Private poll thread started for text answers for question **{question}**. {', '.join(mentions)}"
            )

        # Lagre mapping mellom poll_message og thread
        self.poll_threads[poll_message.id] = thread
        # initialize vote count
        self.poll_votes[poll_message.id] = 0
        logger.info(f"Private poll thread created for message {poll_message.id}")
        return thread

    async def send_response_to_poll_thread(
        self,
        user: discord.User,
        question: str,
        answer: str,
        poll_message: discord.Message,
    ):
        thread = self.poll_threads.get(poll_message.id)

        if not thread:
            logger.error(f"No thread found for poll message ID {poll_message.id}")
            return

        # Send plain message
        await thread.send(f"User {user.display_name} sent this: {answer}")

        # increment stored vote count
        self.poll_votes[poll_message.id] = self.poll_votes.get(poll_message.id, 0) + 1

        # update the poll embed's Votes field (index 1)
        try:
            embed = poll_message.embeds[0]
            votes_count = self.poll_votes[poll_message.id]
            embed.set_field_at(1, name="Votes", value=str(votes_count), inline=True)
            await poll_message.edit(embed=embed)
        except Exception as e:
            logger.error(f"⚠️ Failed to update poll message votes: {e}")

    @poll.error
    async def poll_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need administrator permissions to create polls.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠️ Something went wrong while creating the poll.", ephemeral=True
            )
            logger.error(f"Poll command error: {error}")


async def setup(bot):
    await bot.add_cog(Polls(bot))
