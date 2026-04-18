import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime
import logging

logger = logging.getLogger("UserStats")

from config import GUILD_ID as _GUILD_ID

DATA_FOLDER = "./cogs/simple_stats/user_data"

GUILD_ID = discord.Object(id=_GUILD_ID)


class UserStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not os.path.exists(DATA_FOLDER):
            os.makedirs(DATA_FOLDER)
            logger.info(f"📂 Created data folder: {DATA_FOLDER}")

    # --- Utility functions ---
    def get_user_file(self, user_id: int) -> str:
        return os.path.join(DATA_FOLDER, f"{user_id}.json")

    def load_user_data(self, user_id: int) -> dict:
        path = self.get_user_file(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load data for user {user_id}: {e}")
        return {
            "user_id": user_id,
            "messages_sent": 0,
            "reactions_used": 0,
            "voice_joins": 0,
            "last_message": None,
        }

    def save_user_data(self, user_id: int, data: dict):
        path = self.get_user_file(user_id)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
            logger.debug(f"Saved stats for {user_id}")
        except Exception as e:
            logger.error(f"Failed to save stats for {user_id}: {e}")

    # --- Event tracking ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        user_id = message.author.id
        data = self.load_user_data(user_id)
        data["messages_sent"] += 1
        data["last_message"] = datetime.utcnow().isoformat()
        self.save_user_data(user_id, data)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot:
            return
        data = self.load_user_data(user.id)
        data["reactions_used"] += 1
        self.save_user_data(user.id, data)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel != after.channel:
            data = self.load_user_data(member.id)
            data["voice_joins"] += 1
            self.save_user_data(member.id, data)

    # --- Slash Command ---
    @app_commands.command(name="stats", description="Show stats for a user")
    @app_commands.guilds(GUILD_ID)
    async def stats(self, interaction: discord.Interaction, user: discord.User):
        data = self.load_user_data(user.id)

        embed = discord.Embed(
            title=f"📊 Stats for {user.display_name}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(
            name="💬 Messages Sent", value=f"{data['messages_sent']:,}", inline=True
        )
        embed.add_field(
            name="😊 Reactions Used", value=f"{data['reactions_used']:,}", inline=True
        )
        embed.add_field(
            name="🎙️ Voice Joins", value=f"{data['voice_joins']:,}", inline=True
        )
        embed.add_field(
            name="🕓 Last Message",
            value=f"<t:{int(datetime.fromisoformat(data['last_message']).timestamp())}:R>"
            if data["last_message"]
            else "No messages yet",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserStats(bot))
