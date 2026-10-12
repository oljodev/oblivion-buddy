"""Shared image helpers for the welcome cards and the /rank card."""

import io
import logging

import discord
from easy_pil import Font
from PIL import Image

logger = logging.getLogger("Images")


def fit_text(text: str, variant: str, size: int, min_size: int, max_width: int):
    """Krymper fonten til teksten får plass. Kuttes med '…' hvis den fortsatt er for lang.

    Returnerer (tekst, font).
    """
    font = Font.poppins(variant=variant, size=size)
    while font.getlength(text) > max_width and size > min_size:
        size -= 2
        font = Font.poppins(variant=variant, size=size)
    if font.getlength(text) > max_width:
        while text and font.getlength(text + "…") > max_width:
            text = text[:-1]
        text += "…"
    return text, font


async def fetch_avatar(user: discord.abc.User) -> Image.Image:
    """Henter avataren via discord.py sin egen HTTP-sesjon. Faller tilbake til en ensfarget firkant."""
    try:
        asset = user.display_avatar.with_size(256).with_static_format("png")
        data = await asset.read()
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.warning(f"Could not fetch avatar for {user} ({user.id}): {e}")
        return Image.new("RGBA", (256, 256), "#5865F2")
