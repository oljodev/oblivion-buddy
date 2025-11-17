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
    """Generates the WELCOME image with 'WELCOME' above the user's name and adaptive sizing."""
    try:
        bg_path = get_resource_path(BACKGROUND_IMAGE_NAME)
        font_path = get_resource_path(FONT_NAME)

        img = Image.open(bg_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        width, height = img.size

        # Text pieces separated: heading above username
        heading_text = "WELCOME"
        username_text = member.display_name.upper()
        to_text = "to"
        server_text = server_name.upper()

        # Fonts: base sizes
        font_heading = ImageFont.truetype(font_path, FONT_SIZE_LARGE)
        font_small = ImageFont.truetype(font_path, FONT_SIZE_SMALL)

        # Helper: find largest font size so that text fits within max_width (with margin)
        def fit_font_size(
            text: str, max_width: int, start_size: int, min_size: int = 20
        ):
            size = start_size
            while size >= min_size:
                f = ImageFont.truetype(font_path, size)
                bbox = draw.textbbox((0, 0), text, font=f)
                text_w = bbox[2] - bbox[0]
                if text_w <= max_width:
                    return f, size
                size -= 2
            # fallback to min size
            return ImageFont.truetype(font_path, min_size), min_size

        # Decide max width for username (leave some horizontal margin)
        max_text_width = width - 80

        # Fit username font: start at heading size (so username won't exceed heading by default)
        username_font, username_size = fit_font_size(
            username_text, max_text_width, start_size=FONT_SIZE_LARGE
        )

        # Ensure username is not larger than heading; if it is, reduce it a bit
        if username_size >= FONT_SIZE_LARGE:
            username_font = ImageFont.truetype(font_path, FONT_SIZE_LARGE - 6)
            username_size = FONT_SIZE_LARGE - 6

        # Measure bounding boxes
        bbox_heading = draw.textbbox((0, 0), heading_text, font=font_heading)
        text_w_heading = bbox_heading[2] - bbox_heading[0]
        text_h_heading = bbox_heading[3] - bbox_heading[1]

        bbox_username = draw.textbbox((0, 0), username_text, font=username_font)
        text_w_username = bbox_username[2] - bbox_username[0]
        text_h_username = bbox_username[3] - bbox_username[1]

        # "to" and server text measurements
        bbox_to = draw.textbbox((0, 0), to_text, font=font_small)
        text_w_to = bbox_to[2] - bbox_to[0]
        text_h_to = bbox_to[3] - bbox_to[1]

        bbox_server = draw.textbbox((0, 0), server_text, font=font_small)
        text_w_server = bbox_server[2] - bbox_server[0]
        text_h_server = bbox_server[3] - bbox_server[1]

        # Compute vertical layout for heading + username + "to" + server as a centered block
        gap_between_heading_and_username = 8
        gap_between_username_and_to = 20

        block_height = (
            text_h_heading
            + gap_between_heading_and_username
            + text_h_username
            + gap_between_username_and_to
            + text_h_to
            + 20
            + text_h_server
        )

        start_y = (height - block_height) // 2  # center the whole block vertically

        # Positions
        pos_x_heading = (width - text_w_heading) // 2
        pos_y_heading = start_y

        pos_x_username = (width - text_w_username) // 2
        pos_y_username = (
            pos_y_heading + text_h_heading + gap_between_heading_and_username
        )

        pos_x_to = (width - text_w_to) // 2
        pos_y_to = pos_y_username + text_h_username + gap_between_username_and_to

        pos_x_server = (width - text_w_server) // 2
        pos_y_server = pos_y_to + text_h_to + 20

        # Draw shadow + main text (same style as before)
        shadow_offset = 2

        # Shadow layer
        draw.text(
            (pos_x_heading + shadow_offset, pos_y_heading + shadow_offset),
            heading_text,
            fill=GOLD_SHADOW_COLOR,
            font=font_heading,
        )
        draw.text(
            (pos_x_username + shadow_offset, pos_y_username + shadow_offset),
            username_text,
            fill=GOLD_SHADOW_COLOR,
            font=username_font,
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

        # Main gold text layer
        draw.text(
            (pos_x_heading, pos_y_heading),
            heading_text,
            fill=GOLD_TEXT_COLOR,
            font=font_heading,
        )
        draw.text(
            (pos_x_username, pos_y_username),
            username_text,
            fill=GOLD_TEXT_COLOR,
            font=username_font,
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
    """Generates the GOODBYE image with 'GOODBYE' above the user's name and adaptive sizing."""
    try:
        bg_path = get_resource_path(GOODBYE_IMAGE_NAME)
        font_path = get_resource_path(FONT_NAME)

        img = Image.open(bg_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        width, height = img.size

        # Text pieces separated: heading above username
        heading_text = "GOODBYE"
        username_text = member.display_name.upper()
        from_text = "from"
        server_text = server_name.upper()

        # Fonts: base sizes
        font_heading = ImageFont.truetype(font_path, FONT_SIZE_LARGE)
        font_small = ImageFont.truetype(font_path, FONT_SIZE_SMALL)

        # Helper: find largest font size so that text fits within max_width (with margin)
        def fit_font_size(
            text: str, max_width: int, start_size: int, min_size: int = 20
        ):
            size = start_size
            while size >= min_size:
                f = ImageFont.truetype(font_path, size)
                bbox = draw.textbbox((0, 0), text, font=f)
                text_w = bbox[2] - bbox[0]
                if text_w <= max_width:
                    return f, size
                size -= 2
            return ImageFont.truetype(font_path, min_size), min_size

        # Decide max width for username (leave some horizontal margin)
        max_text_width = width - 80

        # Fit username font
        username_font, username_size = fit_font_size(
            username_text, max_text_width, start_size=FONT_SIZE_LARGE
        )

        # Ensure username is not larger than heading; if it is, reduce it slightly
        if username_size >= FONT_SIZE_LARGE:
            username_font = ImageFont.truetype(font_path, FONT_SIZE_LARGE - 6)
            username_size = FONT_SIZE_LARGE - 6

        # Measure bounding boxes
        bbox_heading = draw.textbbox((0, 0), heading_text, font=font_heading)
        text_w_heading = bbox_heading[2] - bbox_heading[0]
        text_h_heading = bbox_heading[3] - bbox_heading[1]

        bbox_username = draw.textbbox((0, 0), username_text, font=username_font)
        text_w_username = bbox_username[2] - bbox_username[0]
        text_h_username = bbox_username[3] - bbox_username[1]

        bbox_from = draw.textbbox((0, 0), from_text, font=font_small)
        text_w_from = bbox_from[2] - bbox_from[0]
        text_h_from = bbox_from[3] - bbox_from[1]

        bbox_server = draw.textbbox((0, 0), server_text, font=font_small)
        text_w_server = bbox_server[2] - bbox_server[0]
        text_h_server = bbox_server[3] - bbox_server[1]

        # Compute vertical layout for heading + username + "from" + server as a centered block
        gap_between_heading_and_username = 8
        gap_between_username_and_from = 20

        block_height = (
            text_h_heading
            + gap_between_heading_and_username
            + text_h_username
            + gap_between_username_and_from
            + text_h_from
            + 20
            + text_h_server
        )

        start_y = (height - block_height) // 2  # center the whole block vertically

        # Positions
        pos_x_heading = (width - text_w_heading) // 2
        pos_y_heading = start_y

        pos_x_username = (width - text_w_username) // 2
        pos_y_username = (
            pos_y_heading + text_h_heading + gap_between_heading_and_username
        )

        pos_x_from = (width - text_w_from) // 2
        pos_y_from = pos_y_username + text_h_username + gap_between_username_and_from

        pos_x_server = (width - text_w_server) // 2
        pos_y_server = pos_y_from + text_h_from + 20

        # Draw shadow + main text (same style as before)
        shadow_offset = 2

        # Shadow layer
        draw.text(
            (pos_x_heading + shadow_offset, pos_y_heading + shadow_offset),
            heading_text,
            fill=GOLD_SHADOW_COLOR,
            font=font_heading,
        )
        draw.text(
            (pos_x_username + shadow_offset, pos_y_username + shadow_offset),
            username_text,
            fill=GOLD_SHADOW_COLOR,
            font=username_font,
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

        # Main gold text layer
        draw.text(
            (pos_x_heading, pos_y_heading),
            heading_text,
            fill=GOLD_TEXT_COLOR,
            font=font_heading,
        )
        draw.text(
            (pos_x_username, pos_y_username),
            username_text,
            fill=GOLD_TEXT_COLOR,
            font=username_font,
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
