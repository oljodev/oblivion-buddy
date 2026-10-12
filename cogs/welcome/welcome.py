import asyncio
import io
import logging
import random
from pathlib import Path

import discord
from discord.ext import commands
from easy_pil import Editor
from PIL import Image

from cogs._shared.images import fetch_avatar, fit_text
from config import Channel

logger = logging.getLogger("Welcome")

# Bildemappe relativt til denne filen, så det fungerer uansett hvor boten startes fra
IMAGES_DIR = Path(__file__).parent / "welcome_images"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

CARD_SIZE = (800, 450)
AVATAR_SIZE = 150
TEXT_MAX_WIDTH = CARD_SIZE[0] - 40  # 20px margin på hver side


def render_card(background_path: Path, avatar: Image.Image, title: str, subtitle: str) -> io.BytesIO:
    """Tegner velkomst-/farvelkortet. Synkron (PIL), så den kjøres i en egen tråd."""
    background = Editor(str(background_path)).resize(CARD_SIZE, crop=True)
    profile = Editor(avatar).resize((AVATAR_SIZE, AVATAR_SIZE)).circle_image()

    avatar_x = (CARD_SIZE[0] - AVATAR_SIZE) // 2
    background.paste(profile, (avatar_x, 90))
    background.ellipse((avatar_x, 90), AVATAR_SIZE, AVATAR_SIZE, outline="white", stroke_width=5)

    title, title_font = fit_text(title, "bold", 50, 24, TEXT_MAX_WIDTH)
    subtitle, subtitle_font = fit_text(subtitle, "light", 24, 14, TEXT_MAX_WIDTH)

    center_x = CARD_SIZE[0] // 2
    background.text((center_x, 260), title, color="white", font=title_font, align="center")
    background.text((center_x, 330), subtitle, color="white", font=subtitle_font, align="center")

    return background.image_bytes


class ServerGreetings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Tydelig advarsel i loggen hvis kanalen ikke finnes (f.eks. feil server/ID)
        if self.bot.get_channel(Channel.WELCOME) is None:
            logger.warning(
                f"Welcome channel {int(Channel.WELCOME)} not found — welcome/goodbye "
                "cards will not be sent. Check Channel.WELCOME in config.py."
            )

    def _pick_background(self) -> Path | None:
        try:
            images = [p for p in IMAGES_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS]
        except FileNotFoundError:
            images = []
        if not images:
            logger.error(f"No background images found in {IMAGES_DIR}")
            return None
        return random.choice(images)

    async def _send_card(self, member: discord.Member, title: str, message: str, filename: str):
        channel = self.bot.get_channel(Channel.WELCOME)
        if channel is None:
            logger.warning(f"Could not find welcome channel {int(Channel.WELCOME)}; skipping card for {member}.")
            return

        background_path = self._pick_background()
        if background_path is None:
            await channel.send(message)
            return

        try:
            avatar = await fetch_avatar(member)
            image = await asyncio.to_thread(render_card, background_path, avatar, title, member.name)
            await channel.send(message, file=discord.File(fp=image, filename=filename))
        except Exception:
            logger.exception(f"Failed to send {filename} for {member}; sending text only.")
            try:
                await channel.send(message)
            except Exception:
                logger.exception("Fallback text message also failed.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._send_card(
            member,
            f"WELCOME TO {member.guild.name.upper()}",
            f"Welcome to the server, {member.mention}!",
            "welcome_card.png",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Mention virker ikke for brukere som har forlatt serveren, så vi bruker navnet
        await self._send_card(
            member,
            f"GOODBYE FROM {member.guild.name.upper()}",
            f"Goodbye, **{member.name}**. We hope to see you again!",
            "goodbye_card.png",
        )


async def setup(bot):
    await bot.add_cog(ServerGreetings(bot))
