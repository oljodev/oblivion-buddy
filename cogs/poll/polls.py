import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from discord.ui import View, Button, Modal, TextInput
import logging
import json
import os
import asyncio

logger = logging.getLogger("Polls")

GUILD_ID = discord.Object(id=1422932147550818507)

OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090

POLL_STATE_FILE = "/home/olav/dev/oblivion-buddy/cogs/poll/polls.json"


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
        end_ts = int(end_time.timestamp())

        question = self.question.value.strip()
        description = self.description.value.strip()

        embed = discord.Embed(
            title=f"{question}",
            description=description or "No description provided.",
            color=discord.Color.blurple(),
        )

        # Integrated HammerTime here
        embed.add_field(
            name="Ends",
            value=f"<t:{end_ts}:R> (<t:{end_ts}:f>)",
            inline=False,
        )
        embed.add_field(name="Votes", value="0", inline=True)
        embed.add_field(name="Hosted by", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"Today at {datetime.utcnow().strftime('%H:%M UTC')}")

        view = PollView(
            self.poll_cog, end_time, interaction.user, question, description
        )

        await interaction.response.send_message("✅ Poll created!", ephemeral=True)

        poll_message = await interaction.channel.send(embed=embed, view=view)
        view.message = poll_message

        await self.poll_cog.create_poll_thread(
            poll_message, question, end_time, interaction.user.id
        )

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
            "✅ Your answer has been submitted!",
            ephemeral=True,
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
        self.ended = False
        self.message = None

        text_button = Button(label="📝 Send Answer", style=discord.ButtonStyle.primary)
        text_button.callback = self.text_answer
        self.add_item(text_button)

        # Start the finish task instead of a 1-second loop
        self.finish_task = asyncio.create_task(self.wait_for_end())

    async def text_answer(self, interaction: discord.Interaction):
        if self.ended:
            return await interaction.response.send_message(
                "This poll has already ended.", ephemeral=True
            )

        modal = TextResponseModal(
            self.poll_cog, self.question, interaction.user, self.message
        )
        await interaction.response.send_modal(modal)

    def disable_all_buttons(self):
        for item in self.children:
            item.disabled = True

    async def wait_for_end(self):
        """Waits until the end_time to finalize the poll."""
        now = datetime.utcnow()
        delay = (self.end_time - now).total_seconds()

        if delay > 0:
            await asyncio.sleep(delay)

        await self.finalize_poll()

    async def finalize_poll(self):
        """Disables buttons, changes color to gray, and saves final state."""
        if self.ended:
            return
        self.ended = True
        self.disable_all_buttons()

        # Update embed to gray (ended state)
        ended_embed = discord.Embed(
            title=f"**{self.question}**",
            description="This poll has ended.",
            color=discord.Color.dark_gray(),
        )
        ended_embed.add_field(
            name="Ended",
            value=f"<t:{int(self.end_time.timestamp())}:f>",
            inline=False,
        )

        votes_count = (
            self.poll_cog.poll_votes.get(self.message.id, 0) if self.message else 0
        )
        ended_embed.add_field(name="Votes", value=str(votes_count), inline=True)
        ended_embed.add_field(name="Hosted by", value=self.creator.mention, inline=True)
        ended_embed.set_footer(text="Poll Ended")

        try:
            if self.message:
                await self.message.edit(embed=ended_embed, view=self)
                await self.poll_cog.remove_poll_state(self.message.id)
        except Exception as e:
            logger.error(f"⚠️ Failed to finalize poll: {e}")

    async def on_timeout(self):
        self.disable_all_buttons()
        if hasattr(self, "message") and self.message:
            await self.message.edit(view=self)


# ------------------------- Polls Cog -------------------------
class Polls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.poll_threads = {}
        self.poll_votes = {}
        logger.info("Polls Cog initialized")

    @app_commands.command(name="poll", description="Create a new poll")
    @app_commands.guilds(GUILD_ID)
    async def poll(self, interaction: discord.Interaction):
        allowed_roles = [OWNER_ROLE_ID, ADMIN_ROLE_ID]

        if not any(role.id in allowed_roles for role in interaction.user.roles):
            await interaction.response.send_message(
                "🚫 You don't have permission to start polls.", ephemeral=True
            )
            return

        modal = PollModal(self, interaction.user)
        await interaction.response.send_modal(modal)

    async def create_poll_thread(
        self,
        poll_message: discord.Message,
        question: str,
        end_time: datetime,
        creator_id: int,
    ):
        channel = poll_message.channel
        guild = poll_message.guild

        thread = await channel.create_thread(
            name=f"Poll Answers - {question}",
            auto_archive_duration=1440,
            type=discord.ChannelType.private_thread,
        )

        mentions = []
        for role_id in [OWNER_ROLE_ID, ADMIN_ROLE_ID]:
            role = guild.get_role(role_id)
            if role:
                mentions.append(role.mention)

        if mentions:
            await thread.send(
                f"⚠️ Private poll thread started for answers on question: **{question}**. {', '.join(mentions)}"
            )

        self.poll_threads[poll_message.id] = thread
        self.poll_votes[poll_message.id] = 0

        state = self._load_state()
        state[str(poll_message.id)] = {
            "guild_id": guild.id,
            "channel_id": channel.id,
            "thread_id": thread.id,
            "end_timestamp": int(end_time.timestamp()),
            "question": question,
            "creator_id": creator_id,
            "votes": 0,
        }
        self._save_state(state)

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

        await thread.send(f"User {user.display_name} sent this: {answer}")

        # Update vote count in-memory
        self.poll_votes[poll_message.id] = self.poll_votes.get(poll_message.id, 0) + 1

        # Persist vote count
        try:
            state = self._load_state()
            entry = state.get(str(poll_message.id))
            if entry:
                entry["votes"] = self.poll_votes[poll_message.id]
                self._save_state(state)
        except Exception as e:
            logger.error(f"⚠️ Failed to persist vote count: {e}")

        # Instantly update the embed Votes field (index 1)
        try:
            embed = poll_message.embeds[0]
            votes_count = self.poll_votes[poll_message.id]
            embed.set_field_at(1, name="Votes", value=str(votes_count), inline=True)
            await poll_message.edit(embed=embed)
        except Exception as e:
            logger.error(f"⚠️ Failed to update poll message votes: {e}")

    def _load_state(self):
        try:
            if not os.path.exists(POLL_STATE_FILE):
                return {}
            with open(POLL_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"⚠️ Failed to load poll state: {e}")
            return {}

    def _save_state(self, state: dict):
        try:
            dirpath = os.path.dirname(POLL_STATE_FILE)
            if dirpath and not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            with open(POLL_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"⚠️ Failed to save poll state: {e}")

    async def remove_poll_state(self, message_id: int):
        state = self._load_state()
        if str(message_id) in state:
            del state[str(message_id)]
            self._save_state(state)
        self.poll_votes.pop(message_id, None)
        self.poll_threads.pop(message_id, None)

    async def restore_polls_from_state(self):
        state = self._load_state()
        if not state:
            return

        for msg_id_str, entry in list(state.items()):
            try:
                msg_id = int(msg_id_str)
                guild = self.bot.get_guild(entry["guild_id"])
                if not guild:
                    continue

                channel = guild.get_channel(entry["channel_id"])
                if not channel:
                    continue

                try:
                    poll_message = await channel.fetch_message(msg_id)
                except Exception:
                    await self.remove_poll_state(msg_id)
                    continue

                end_time = datetime.utcfromtimestamp(entry["end_timestamp"])
                if end_time <= datetime.utcnow():
                    await self.remove_poll_state(msg_id)
                    continue

                creator = guild.get_member(entry.get("creator_id")) or self.bot.user
                description = (
                    poll_message.embeds[0].description if poll_message.embeds else ""
                )

                view = PollView(
                    self, end_time, creator, entry.get("question", ""), description
                )
                view.message = poll_message

                self.poll_votes[poll_message.id] = entry.get("votes", 0)
                thread_obj = guild.get_channel(entry.get("thread_id"))
                if thread_obj:
                    self.poll_threads[poll_message.id] = thread_obj

                await poll_message.edit(view=view)
                logger.info(f"Restored poll view for message {msg_id}")
            except Exception as e:
                logger.error(f"⚠️ Error restoring poll {msg_id_str}: {e}")


async def setup(bot):
    cog = Polls(bot)
    await bot.add_cog(cog)
    try:
        await cog.restore_polls_from_state()
    except Exception as e:
        logger.error(f"⚠️ Failed to restore polls from state: {e}")
