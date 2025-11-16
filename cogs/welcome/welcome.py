import discord
from discord.ext import commands
import logging
import io
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path  # Veldig nyttig for å bygge stier

# --- KONSTANTER (TILPASS DISSE) ---
WELCOME_CHANNEL_ID = 1422933181497086122
SERVER_NAME = "Oblivion SMP"

BACKGROUND_IMAGE_NAME = "welcome_bg.png"
GOODBYE_IMAGE_NAME = "goodbye_bg.png"
FONT_NAME = "CinzelDecorative-Black.ttf"

logger = logging.getLogger(__name__)


# --- Helper function to get the correct resource path ---
def get_resource_path(filename: str) -> Path:
    """
    Constructs the absolute path to a resource file located in the same directory as this file.
    """
    base_dir = Path(__file__).parent
    return base_dir / filename


FONT_SIZE_LARGE = 80
FONT_SIZE_SMALL = 45

GOLD_TEXT_COLOR = (220, 190, 120)  # Basefarge
GOLD_SHADOW_COLOR = (186, 158, 90)  # Skygge


def generate_welcome_image(member: discord.Member, server_name: str) -> io.BytesIO:
    """Generates the WELCOME image with user's name, centered, with gold shadow text."""
    try:
        bg_path = get_resource_path(BACKGROUND_IMAGE_NAME)
        font_path = get_resource_path(FONT_NAME)

        img = Image.open(bg_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        width, height = img.size

        # Text
        welcome_text = f"WELCOME {member.display_name.upper()}"
        to_text = "to"
        server_text = server_name.upper()

        # Fonts
        font_large = ImageFont.truetype(font_path, FONT_SIZE_LARGE)
        font_small = ImageFont.truetype(font_path, FONT_SIZE_SMALL)

        # 3. Calculate positions (Centering the text)

        # WELCOME USERNAME
        bbox_welcome = draw.textbbox((0, 0), welcome_text, font=font_large)
        text_w_welcome = bbox_welcome[2] - bbox_welcome[0]
        text_h_welcome = bbox_welcome[3] - bbox_welcome[1]

        pos_x_welcome = (width - text_w_welcome) // 2
        pos_y_welcome = height // 2 - 150

        # "to"
        bbox_to = draw.textbbox((0, 0), to_text, font=font_small)
        text_w_to = bbox_to[2] - bbox_to[0]
        text_h_to = bbox_to[3] - bbox_to[1]

        pos_x_to = (width - text_w_to) // 2
        pos_y_to = pos_y_welcome + text_h_welcome + 15

        # Oblivion SMP (Avstand justert til +20 piksler)
        bbox_server = draw.textbbox((0, 0), server_text, font=font_small)
        text_w_server = bbox_server[2] - bbox_server[0]

        pos_y_server = pos_y_to + text_h_to + 20  # Justert avstand
        pos_x_server = (width - text_w_server) // 2

        # 4. Draw text (MED SKYGGE/OUTLINE)
        shadow_offset = 2  # Piksler skyggen forskyves

        # TEGN 1: Skygge (Mørk farge, forskjøvet)
        draw.text(
            (pos_x_welcome + shadow_offset, pos_y_welcome + shadow_offset),
            welcome_text,
            fill=GOLD_SHADOW_COLOR,
            font=font_large,
        )
        draw.text(
            (pos_x_to + shadow_offset, pos_y_to + shadow_offset),
            to_text,
            fill=GOLD_SHADOW_COLOR,
            font=font_small,
        )
        draw.text(
            (pos_x_server + shadow_offset, pos_y_server + shadow_offset),
            server_text,
            fill=GOLD_SHADOW_COLOR,
            font=font_small,
        )

        # TEGN 2: Hovedteksten (Lys gullfarge, på toppen)
        draw.text(
            (pos_x_welcome, pos_y_welcome),
            welcome_text,
            fill=GOLD_TEXT_COLOR,
            font=font_large,
        )
        draw.text((pos_x_to, pos_y_to), to_text, fill=GOLD_TEXT_COLOR, font=font_small)
        draw.text(
            (pos_x_server, pos_y_server),
            server_text,
            fill=GOLD_TEXT_COLOR,
            font=font_small,
        )

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    except FileNotFoundError:
        logger.error(
            f"Background file or font not found for Welcome. Check paths: {get_resource_path(BACKGROUND_IMAGE_NAME)} and {get_resource_path(FONT_NAME)}."
        )
        return None
    except Exception as e:
        logger.error(f"Error during welcome image generation: {e}")
        return None


# --- Helper function for goodbye image processing ---
def generate_goodbye_image(member: discord.Member, server_name: str) -> io.BytesIO:
    """Generates the GOODBYE image with user's name, centered, with gold shadow text."""
    try:
        bg_path = get_resource_path(GOODBYE_IMAGE_NAME)
        font_path = get_resource_path(FONT_NAME)

        img = Image.open(bg_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        width, height = img.size

        # Text
        goodbye_text = f"GOODBYE {member.display_name.upper()}"
        from_text = "from"
        server_text = server_name.upper()

        # Fonts
        font_large = ImageFont.truetype(font_path, FONT_SIZE_LARGE)
        font_small = ImageFont.truetype(font_path, FONT_SIZE_SMALL)

        # 3. Calculate positions (Centering the text)

        # GOODBYE USERNAME
        bbox_goodbye = draw.textbbox((0, 0), goodbye_text, font=font_large)
        text_w_goodbye = bbox_goodbye[2] - bbox_goodbye[0]
        text_h_goodbye = bbox_goodbye[3] - bbox_goodbye[1]

        pos_x_goodbye = (width - text_w_goodbye) // 2
        pos_y_goodbye = height // 2 - 150

        # "from"
        bbox_from = draw.textbbox((0, 0), from_text, font=font_small)
        text_w_from = bbox_from[2] - bbox_from[0]
        text_h_from = bbox_from[3] - bbox_from[1]

        pos_x_from = (width - text_w_from) // 2
        pos_y_from = pos_y_goodbye + text_h_goodbye + 15

        # Oblivion SMP (Avstand justert til +20 piksler)
        bbox_server = draw.textbbox((0, 0), server_text, font=font_small)
        text_w_server = bbox_server[2] - bbox_server[0]

        pos_y_server = pos_y_from + text_h_from + 20  # Justert avstand
        pos_x_server = (width - text_w_server) // 2

        # 4. Draw text (MED SKYGGE/OUTLINE)
        shadow_offset = 2  # Piksler skyggen forskyves

        # TEGN 1: Skygge (Mørk farge, forskjøvet)
        draw.text(
            (pos_x_goodbye + shadow_offset, pos_y_goodbye + shadow_offset),
            goodbye_text,
            fill=GOLD_SHADOW_COLOR,
            font=font_large,
        )
        draw.text(
            (pos_x_from + shadow_offset, pos_y_from + shadow_offset),
            from_text,
            fill=GOLD_SHADOW_COLOR,
            font=font_small,
        )
        draw.text(
            (pos_x_server + shadow_offset, pos_y_server + shadow_offset),
            server_text,
            fill=GOLD_SHADOW_COLOR,
            font=font_small,
        )

        # TEGN 2: Hovedteksten (Lys gullfarge, på toppen)
        draw.text(
            (pos_x_goodbye, pos_y_goodbye),
            goodbye_text,
            fill=GOLD_TEXT_COLOR,
            font=font_large,
        )
        draw.text(
            (pos_x_from, pos_y_from), from_text, fill=GOLD_TEXT_COLOR, font=font_small
        )
        draw.text(
            (pos_x_server, pos_y_server),
            server_text,
            fill=GOLD_TEXT_COLOR,
            font=font_small,
        )

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    except FileNotFoundError:
        logger.error(
            f"Background file or font not found for Goodbye. Check paths: {get_resource_path(GOODBYE_IMAGE_NAME)} and {get_resource_path(FONT_NAME)}."
        )
        return None
    except Exception as e:
        logger.error(f"Error during goodbye image generation: {e}")
        return None


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_welcome_channel(self):
        """Fetches the welcome channel safely."""
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(WELCOME_CHANNEL_ID)
        if not channel:
            logger.error(f"Welcome channel with ID {WELCOME_CHANNEL_ID} not found.")
        return channel

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = await self.get_welcome_channel()
        if not channel or member.bot:
            return

        # --- Ny logikk for å finne medlemsnummer ---
        sorted_members = sorted(member.guild.members, key=lambda m: m.joined_at)

        member_number = sorted_members.index(member) + 1

        # Meldingen som sendes FØR bildet
        member_tag = f"Member #{member_number}"

        # --- Slutt på ny logikk ---

        logger.info(
            f"Member {member.name} joined the server, generating welcome image..."
        )

        buffer = await self.bot.loop.run_in_executor(
            None, generate_welcome_image, member, SERVER_NAME
        )

        if buffer:
            discord_file = discord.File(buffer, filename="welcome_card.png")

            # OPPDATERT: Inkluderer medlemsnummer-taggen i content-strengen
            await channel.send(
                content=f"Welcome {member.mention}! You are now part of **{SERVER_NAME}**! 🎉\n{member_tag}",
                file=discord_file,
            )

        else:
            await channel.send(
                f"Welcome {member.mention}! Sorry, the custom image failed to load. Please check logs for errors. 😔"
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = await self.get_welcome_channel()
        if not channel or member.bot:
            return

        logger.info(
            f"Member {member.name} left the server, generating goodbye image..."
        )

        # Generate the goodbye image
        buffer = await self.bot.loop.run_in_executor(
            None, generate_goodbye_image, member, SERVER_NAME
        )

        if buffer:
            discord_file = discord.File(buffer, filename="goodbye_card.png")

            await channel.send(
                content=f"Goodbye, **{member.display_name}**. We hope to see you again soon! 👋",
                file=discord_file,
            )
        else:
            # Fallback if image generation fails
            await channel.send(
                f"Goodbye, **{member.display_name}**. The farewell image failed to load. 👋"
            )


# --- Setup Function (Important for Cogs) ---
async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
