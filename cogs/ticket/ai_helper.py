import os
import time
import discord
from discord.ext import commands
from google import genai
from google.genai import types
from .ticket import load_data

SYSTEM_PROMPT = (
    "You are a helpful technical support assistant for Oblivion SMP, a Minecraft modpack server. "
    "Players come to you with technical problems — typically modpack update errors, wrong mod versions, "
    "missing mods, or crash logs. "
    "Give clear, numbered, step-by-step solutions. Keep answers concise and easy to follow. "
    "If the player attaches a screenshot or crash log, analyze it carefully. "
    "If you cannot determine the fix from the information given, ask one specific clarifying question."
)

RATE_LIMIT_SECONDS = 15


class AIHelper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        # {thread_id: {"history": [...], "last_used": {user_id: timestamp}}}
        self.threads: dict[int, dict] = {}

    def _get_thread_state(self, thread_id: int) -> dict:
        if thread_id not in self.threads:
            self.threads[thread_id] = {"history": [], "last_used": {}}
        return self.threads[thread_id]

    async def _get_ticket_context(self, thread: discord.Thread) -> str | None:
        async for msg in thread.history(limit=5, oldest_first=True):
            if msg.author.bot and msg.embeds:
                embed = msg.embeds[0]
                lines = []
                for field in embed.fields:
                    lines.append(f"{field.name}: {field.value}")
                return "\n".join(lines) if lines else None
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.content.lower().startswith("!ai"):
            return

        data = load_data()
        if message.channel.id not in data["active_threads"]:
            return

        state = self._get_thread_state(message.channel.id)

        # Rate limit
        last = state["last_used"].get(message.author.id, 0)
        remaining = RATE_LIMIT_SECONDS - (time.time() - last)
        if remaining > 0:
            await message.reply(f"Please wait {remaining:.0f}s before sending another message.", mention_author=False)
            return
        state["last_used"][message.author.id] = time.time()

        user_text = message.content[3:].strip()
        parts = []
        if user_text:
            parts.append(types.Part.from_text(text=user_text))
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                img_bytes = await attachment.read()
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type=attachment.content_type))

        if not parts:
            await message.reply("Please include a question or screenshot after `!ai`.", mention_author=False)
            return

        # Build system prompt with ticket context on first message
        system = SYSTEM_PROMPT
        if not state["history"]:
            context = await self._get_ticket_context(message.channel)
            if context:
                system += f"\n\nThe player's reported issue:\n{context}"

        state["history"].append(types.Content(role="user", parts=parts))

        async with message.channel.typing():
            response = await self.client.aio.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=state["history"],
                config=types.GenerateContentConfig(system_instruction=system),
            )

        state["history"].append(types.Content(role="model", parts=[types.Part.from_text(text=response.text)]))

        await message.reply(response.text, mention_author=False)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound) and ctx.message.content.lower().startswith("!ai"):
            pass


async def setup(bot):
    await bot.add_cog(AIHelper(bot))
