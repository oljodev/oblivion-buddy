import discord
from discord.ext import commands
from discord import app_commands
import io
import json
import os
import math
import asyncio
import logging
import time
from pathlib import Path
from easy_pil import Editor, Font
from PIL import Image
from config import Channel, GUILD_ID as _GUILD_ID
from cogs._shared import dev_mode, xp_store
from cogs._shared.images import fetch_avatar, fit_text
from cogs._shared.json_store import load_json, save_json
from cogs.leveling_system import pets as pets_mod

logger = logging.getLogger("LevelingSystem")

# ==========================================
# ⚙️ CONFIGURATION (EDIT THESE VALUES)
# ==========================================

# Dev-mode gating is centralised in cogs/_shared/dev_mode.py — flip TEST_MODE
# there to gate every XP source (this cog included) to the Dev Team role.
ANNOUNCEMENT_CHANNEL_ID = Channel.BOT_COMMANDS
IGNORE_CHANNEL_IDS = [Channel.TICKET]

GUILD_ID = discord.Object(id=_GUILD_ID)

# Roles based on the provided image
ROLE_MILESTONES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100]
XP_PER_MESSAGE = 10

DATA_FOLDER = "./cogs/simple_stats/user_data"
TRACKING_FILE = "./cogs/leveling_system/level_tracking.json"

BACKGROUND_IMAGE_PATH = Path(__file__).parent / "leveling_image.png"

# ==========================================
# 🧮 MATH & HELPER FUNCTIONS
# ==========================================


def get_level_from_xp(xp: int) -> int:
    """Calculates the user's level based on total XP using the exponential formula."""
    if xp < 100:
        return 0
    # Formula: XP = 50*(Level^2) + 50*Level
    level = (-50 + math.sqrt(2500 + 200 * xp)) / 100
    return math.floor(level)


def get_xp_for_level(level: int) -> int:
    """Calculates total XP required to reach a specific level."""
    return 50 * (level**2) + 50 * level


# ==========================================
# 🎨 RANK CARD RENDERING
# ==========================================

COLOR_WHITE = "#FFFFFF"
COLOR_GREEN = "#00E676"  # En lys og klar grønn farge
COLOR_BAR_BG = "#332A4A"  # Mørk lilla/grå for bakgrunnen på baren

CARD_SIZE = (900, 250)
AVATAR_POS = (40, 35)
AVATAR_SIZE = 180
RIGHT_EDGE = 850  # Høyre marg for tekst og bar
BAR_X, BAR_Y, BAR_WIDTH, BAR_HEIGHT = 250, 150, 600, 40


def render_rank_card(
    avatar: Image.Image,
    is_pet: bool,
    display_name: str,
    level: int,
    rank: int | None,
    xp_in_level: int,
    needed_in_level: int,
) -> io.BytesIO:
    """Tegner rank-kortet. Synkron (PIL), så den kjøres i en egen tråd."""
    background = Editor(str(BACKGROUND_IMAGE_PATH)).resize(CARD_SIZE)

    # -- Profilbilde / pet --
    if is_pet:
        # Pixel art skaleres med NEAREST så den forblir skarp, og beholder sin
        # rektangulære form uten hvit ring.
        sprite = avatar.resize((AVATAR_SIZE, AVATAR_SIZE), Image.NEAREST)
        background.paste(Editor(sprite), AVATAR_POS)
    else:
        profile = Editor(avatar).resize((AVATAR_SIZE, AVATAR_SIZE)).circle_image()
        background.paste(profile, AVATAR_POS)
        background.ellipse(
            AVATAR_POS, AVATAR_SIZE, AVATAR_SIZE, outline=COLOR_WHITE, stroke_width=4
        )

    font_level = Font.poppins(size=50, variant="bold")
    font_small = Font.poppins(size=25, variant="regular")

    # -- Level (øverst til høyre) og Rank rett til venstre for den --
    level_text = f"LEVEL {level}"
    background.text(
        (RIGHT_EDGE, 40), level_text, color=COLOR_WHITE, font=font_level, align="right"
    )
    rank_text = f"RANK #{rank}" if rank is not None else "UNRANKED"
    rank_right = RIGHT_EDGE - int(font_level.getlength(level_text)) - 20
    background.text(
        (rank_right, 47), rank_text, color=COLOR_WHITE, font=font_small, align="right"
    )

    # -- XP-tall over baren, høyrejustert --
    xp_text = f"{xp_in_level:,} / {needed_in_level:,} XP"
    background.text(
        (RIGHT_EDGE, BAR_Y - 35),
        xp_text,
        color=COLOR_WHITE,
        font=font_small,
        align="right",
    )

    # -- Brukernavn: krympes/kuttes så det ikke kolliderer med XP-teksten --
    name_max_width = RIGHT_EDGE - int(font_small.getlength(xp_text)) - 25 - BAR_X
    name, font_name = fit_text(display_name, "regular", 35, 22, name_max_width)
    background.text((BAR_X, 80), name, color=COLOR_WHITE, font=font_name)

    # -- XP-bar --
    background.rectangle(
        (BAR_X, BAR_Y), BAR_WIDTH, BAR_HEIGHT, fill=COLOR_BAR_BG, radius=20
    )
    progress = min(xp_in_level / needed_in_level, 1) if needed_in_level > 0 else 1
    filled_width = int(BAR_WIDTH * progress)
    if filled_width > 0:
        # Minst like bred som høyden, ellers blir den avrundede enden bare en strek
        filled_width = max(filled_width, BAR_HEIGHT)
        background.rectangle(
            (BAR_X, BAR_Y), filled_width, BAR_HEIGHT, fill=COLOR_GREEN, radius=20
        )

    return background.image_bytes


def _scan_all_users() -> list[dict]:
    """Leser alle brukerfiler og returnerer [{user_id, xp, level}] sortert etter XP."""
    users = []
    if not os.path.exists(DATA_FOLDER):
        return users
    for filename in os.listdir(DATA_FOLDER):
        if not filename.endswith(".json"):
            continue
        try:
            user_id = int(filename[: -len(".json")])
            with open(os.path.join(DATA_FOLDER, filename), "r") as f:
                total_xp = xp_store.get_total_xp(json.load(f))
        except (ValueError, OSError) as e:
            logger.warning(f"Skipping {filename} in leaderboard: {e}")
            continue
        if total_xp > 0:
            users.append({"user_id": user_id, "xp": total_xp, "level": get_level_from_xp(total_xp)})
    users.sort(key=lambda u: u["xp"], reverse=True)
    return users


# ==========================================
# 📊 LEADERBOARD PAGINATION UI
# ==========================================


class LeaderboardView(discord.ui.View):
    def __init__(self, data: list, user: discord.User):
        super().__init__(timeout=120)
        self.data = data
        self.user = user
        self.current_page = 0
        self.items_per_page = 10
        self.max_pages = math.ceil(len(data) / self.items_per_page)
        self.update_buttons()
        self.lock = asyncio.Lock()  # <-- NY: Legg til denne

    def update_buttons(self):
        self.btn_prev.disabled = self.current_page == 0
        self.btn_next.disabled = (
            self.current_page >= self.max_pages - 1 or self.max_pages == 0
        )

    def generate_embed(self) -> discord.Embed:
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_data = self.data[start_idx:end_idx]

        embed = discord.Embed(
            title="🏆 Server XP Leaderboard", color=discord.Color.gold()
        )

        description = ""
        for i, user_data in enumerate(page_data, start=start_idx + 1):
            description += f"**#{i}** <@{user_data['user_id']}> - Level {user_data['level']} (Total: {user_data['xp']:,} XP)\n"

        embed.description = description if description else "No data available yet."
        embed.set_footer(
            text=f"Page {self.current_page + 1} of {max(1, self.max_pages)}"
        )
        return embed

    @discord.ui.button(
        label="Previous page", style=discord.ButtonStyle.secondary, disabled=True
    )
    async def btn_prev(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="Next page", style=discord.ButtonStyle.secondary)
    async def btn_next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


# ==========================================
# 🚀 MAIN COG
# ==========================================


class LevelingSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.level_tracking = self.load_tracking_data()

        # Rank-cache (brukes av /rank og /leaderboard)
        self.cached_ranks = []
        self.last_cache_update = None
        self.cache_timeout = 60  # Oppdaterer cachen max hvert 60. sekund
        self.lock = asyncio.Lock()

    async def update_leaderboard_cache(self):
        """Sorted list of users by XP (for rank # and /leaderboard), refreshed at most every 60s."""
        now = time.monotonic()
        if self.last_cache_update and now - self.last_cache_update < self.cache_timeout:
            return  # Cachen er fortsatt fersk nok
        # Fillesingen kjøres i en tråd så den ikke blokkerer boten
        self.cached_ranks = await asyncio.to_thread(_scan_all_users)
        self.last_cache_update = now

    def load_tracking_data(self) -> dict:
        """Loads the file that remembers the highest level announced for each user."""
        return load_json(TRACKING_FILE, {})

    def save_tracking_data(self):
        """Saves the tracking data to disk."""
        try:
            save_json(TRACKING_FILE, self.level_tracking, indent=4)
        except Exception as e:
            logger.error(f"Failed to save tracking data: {e}")

    def get_user_stats(self, user_id: int) -> dict:
        """Returns full per-user stats dict (with all known XP fields)."""
        return xp_store.get_user_stats(user_id)

    def get_total_xp(self, user_id: int) -> int:
        return xp_store.get_total_xp(xp_store.get_user_stats(user_id))

    async def _notify_pet_unlock(
        self, member: discord.Member, pet: dict, level: int | None
    ):
        """DM the user that they unlocked a new pet. Best-effort.

        ``level`` is ``None`` for the starter-pet grant.
        """
        sprite_path = pets_mod.pet_image_path(pet)
        if level is None:
            unlock_line = f"You've been given a starter companion: **{pet['name']}**."
        else:
            unlock_line = f"At level **{level}** you unlocked **{pet['name']}**."
        embed = discord.Embed(
            title="🎁 New companion unlocked!",
            description=(
                f"{unlock_line}\n"
                f"Run `/pets` to view your collection and choose which one shows on your rank card."
            ),
            color=discord.Color.purple(),
        )
        try:
            if sprite_path.exists():
                file = discord.File(sprite_path, filename=pet["file"])
                embed.set_thumbnail(url=f"attachment://{pet['file']}")
                await member.send(embed=embed, file=file)
            else:
                await member.send(embed=embed)
        except discord.Forbidden:
            pass
        except Exception as e:
            logger.debug(f"Could not DM pet unlock to {member.id}: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.author, discord.Member):
            return

        if message.channel.id in IGNORE_CHANNEL_IDS:
            return

        if not dev_mode.is_eligible_member(message.author):
            return

        member = message.author
        user_id_str = str(member.id)

        # Låsen beskytter bare tilstanden (rask, ingen nettverkskall), så én
        # brukers level-up-meldinger ikke holder igjen XP for alle andre.
        async with self.lock:
            # Starter-pet ved første melding (no-op når flagget er satt)
            starter_pet = pets_mod.grant_starter_pet(member.id)

            # Beregn nivå basert på alle XP-kilder
            current_xp = xp_store.get_total_xp(self.get_user_stats(member.id))
            target_level = get_level_from_xp(current_xp)
            last_announced = self.level_tracking.get(user_id_str, 0)

            new_levels = list(range(last_announced + 1, target_level + 1))
            granted_pets = []
            if new_levels:
                self.level_tracking[user_id_str] = target_level
                self.save_tracking_data()
                # Gi pet for hvert 5. nivå opp til 100
                for lvl in new_levels:
                    pet = pets_mod.grant_pet_for_level(member.id, lvl)
                    if pet is not None:
                        granted_pets.append((pet, lvl))

        # --- Discord-kall (utenfor låsen) ---
        if starter_pet is not None:
            await self._notify_pet_unlock(member, starter_pet, level=None)
        if not new_levels:
            return

        await self._announce_level_up(member, new_levels)

        # Gi roller for hvert milestone-nivå brukeren passerer
        for lvl in new_levels:
            if lvl not in ROLE_MILESTONES:
                continue
            role = discord.utils.get(message.guild.roles, name=f"Level {lvl}")
            if role is None:
                logger.warning(f"Role 'Level {lvl}' not found — create it to give level rewards.")
                continue
            if role in member.roles:
                continue
            try:
                await member.add_roles(role, reason=f"Reached level {lvl}")
            except discord.Forbidden:
                logger.error(
                    f"Can't give role '{role.name}' to {member} — move the bot's role above it."
                )
            except discord.HTTPException as e:
                logger.error(f"Failed to give role '{role.name}' to {member}: {e}")

        for pet, lvl in granted_pets:
            await self._notify_pet_unlock(member, pet, lvl)

    async def _announce_level_up(self, member: discord.Member, new_levels: list[int]):
        channel = self.bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if channel is None:
            return
        # Store hopp (f.eks. bonus-XP) gir én melding i stedet for en vegg av meldinger
        if len(new_levels) > 3:
            texts = [
                f"🎉 Congrats {member.mention}! You jumped from level **{new_levels[0] - 1}** "
                f"to **{new_levels[-1]}**!"
            ]
        else:
            texts = [f"🎉 Congrats {member.mention}! Your level is now **{lvl}**!" for lvl in new_levels]
        for i, text in enumerate(texts):
            try:
                await channel.send(text)
            except discord.HTTPException as e:
                logger.error(f"Could not send level-up message: {e}")
                return
            if i < len(texts) - 1:
                await asyncio.sleep(1.2)

    # --- Slash Commands ---

    @app_commands.command(
        name="rank",
        description="Check your current level and XP with a stylized image card",
    )
    @app_commands.guilds(GUILD_ID)
    async def rank(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Siden bildegenerering kan ta 1-2 sekunder

        try:
            user = interaction.user
            stats = self.get_user_stats(user.id)
            current_xp = xp_store.get_total_xp(stats)
            current_level = get_level_from_xp(current_xp)

            # XP i *nåværende* nivå
            xp_in_level = current_xp - get_xp_for_level(current_level)
            needed_in_level = get_xp_for_level(current_level + 1) - get_xp_for_level(
                current_level
            )

            # Rank # (posisjon) — regnes ut fra cachen, men brukerens egen XP er
            # alltid fersk, så cachen kan være opptil 60s gammel uten at det gir N/A.
            user_rank = None
            if current_xp > 0:
                await self.update_leaderboard_cache()
                user_rank = 1 + sum(
                    1
                    for u in self.cached_ranks
                    if u["xp"] > current_xp and u["user_id"] != user.id
                )

            # Pet-sprite i stedet for profilbilde hvis brukeren har valgt det i /pets
            active_pet = pets_mod.get_active_pet(user.id)
            pet_path = pets_mod.pet_image_path(active_pet) if active_pet else None
            if pet_path is not None and pet_path.exists():
                avatar, is_pet = Image.open(pet_path).convert("RGBA"), True
            else:
                avatar, is_pet = await fetch_avatar(user), False

            image = await asyncio.to_thread(
                render_rank_card,
                avatar,
                is_pet,
                user.display_name,
                current_level,
                user_rank,
                xp_in_level,
                needed_in_level,
            )
            await interaction.followup.send(
                file=discord.File(fp=image, filename="rank_card.png")
            )
        except Exception:
            logger.exception(f"Failed to generate rank card for {interaction.user}")
            await interaction.followup.send(
                "❌ Something went wrong while generating your rank card. Please try again later.",
                ephemeral=True,
            )

    @app_commands.command(
        name="leaderboard", description="View the server's XP leaderboard"
    )
    @app_commands.guilds(GUILD_ID)
    async def leaderboard(self, interaction: discord.Interaction):
        await self.update_leaderboard_cache()
        if not self.cached_ranks:
            return await interaction.response.send_message(
                "No data available for the leaderboard yet!", ephemeral=True
            )

        view = LeaderboardView(data=self.cached_ranks, user=interaction.user)
        await interaction.response.send_message(embed=view.generate_embed(), view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingSystem(bot))
