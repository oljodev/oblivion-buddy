import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import math
import asyncio
import logging
from datetime import datetime  # <-- NY: Trengs for cache-timing
from easy_pil import Editor, load_image_async, Font  # <-- NY: Easy-pil imports
from config import Channel, GUILD_ID as _GUILD_ID

logger = logging.getLogger("LevelingSystem")

# ==========================================
# ⚙️ CONFIGURATION (EDIT THESE VALUES)
# ==========================================

TEST_MODE = False
ADMIN_ROLES = ["Admin", "Owner"]  # Roles that can trigger XP in Test Mode
ANNOUNCEMENT_CHANNEL_ID = Channel.BOT_COMMANDS
IGNORE_CHANNEL_IDS = [Channel.TICKET]

GUILD_ID = discord.Object(id=_GUILD_ID)

# Roles based on the provided image
ROLE_MILESTONES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100]
XP_PER_MESSAGE = 10

DATA_FOLDER = "./cogs/simple_stats/user_data"
TRACKING_FILE = "./cogs/leveling_system/level_tracking.json"

BACKGROUND_IMAGE_PATH = "./cogs/leveling_system/leveling_image.png"

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

        # --- NY: Cache logikk ---
        self.cached_ranks = []
        self.last_cache_update = None
        self.cache_timeout = 60  # Oppdaterer cachen max hvert 60. sekund
        self.lock = asyncio.Lock()

    # --- NY: Helper for å oppdatere rank-cachen effektivt ---
    async def update_leaderboard_cache(self):
        """Generates a sorted list of users by XP to determine rank #."""
        now = datetime.utcnow()
        if (
            self.last_cache_update
            and (now - self.last_cache_update).total_seconds() < self.cache_timeout
        ):
            return  # Cachen er fortsatt fersk nok

        temp_users = []
        if os.path.exists(DATA_FOLDER):
            for filename in os.listdir(DATA_FOLDER):
                if filename.endswith(".json") and filename != "level_tracking.json":
                    try:
                        # Vi leser bare msgs_sent, så det går raskt
                        with open(os.path.join(DATA_FOLDER, filename), "r") as f:
                            data = json.load(f)
                            msgs = data.get("messages_sent", 0)
                            invite_xp = data.get("invite_xp", 0)
                            total_xp = msgs * XP_PER_MESSAGE + invite_xp
                            if total_xp > 0:
                                temp_users.append(
                                    {
                                        "user_id": data.get("user_id"),
                                        "xp": total_xp,
                                    }
                                )
                    except Exception:
                        pass

        # Sorter etter XP
        temp_users.sort(key=lambda x: x["xp"], reverse=True)
        self.cached_ranks = temp_users
        self.last_cache_update = now

    def load_tracking_data(self) -> dict:
        """Loads the file that remembers the highest level announced for each user."""
        if os.path.exists(TRACKING_FILE):
            try:
                with open(TRACKING_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_tracking_data(self):
        """Saves the tracking data to disk."""
        try:
            with open(TRACKING_FILE, "w") as f:
                json.dump(self.level_tracking, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save tracking data: {e}")

    def get_user_stats(self, user_id: int) -> tuple[int, int]:
        """Reads the existing json file to return (messages_sent, invite_xp)."""
        path = os.path.join(DATA_FOLDER, f"{user_id}.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    return data.get("messages_sent", 0), data.get("invite_xp", 0)
            except Exception:
                pass
        return 0, 0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.author, discord.Member):
            return

        if message.channel.id in IGNORE_CHANNEL_IDS:
            return

        if TEST_MODE:
            is_admin = any(role.name in ADMIN_ROLES for role in message.author.roles)
            if not is_admin:
                return

        async with self.lock:
            user_id_str = str(message.author.id)

            # 1. Beregn nivå basert på meldinger + invite_xp
            messages_sent, invite_xp = self.get_user_stats(message.author.id)
            current_xp = (messages_sent * XP_PER_MESSAGE) + invite_xp
            target_level = get_level_from_xp(current_xp)

            # 2. Last inn data på NYTT for å få med siste endringer fra andre meldinger
            self.level_tracking = self.load_tracking_data()
            last_announced = self.level_tracking.get(user_id_str, 0)

            # 3. Hvis brukeren skal opp i nivå
            if target_level > last_announced:
                announcement_channel = self.bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)

                for lvl in range(last_announced + 1, target_level + 1):
                    self.level_tracking[user_id_str] = lvl
                    self.save_tracking_data()

                    if announcement_channel:
                        try:
                            await announcement_channel.send(
                                f"🎉 Congrats {message.author.mention}! Your level is now **{lvl}**!"
                            )
                            await asyncio.sleep(1.2)
                        except Exception as e:
                            logger.error(f"Kunne ikke sende melding: {e}")

                    # Gi roller for hvert milestone-nivå brukeren passerer
                    if lvl in ROLE_MILESTONES:
                        role_name = f"Level {lvl}"
                        role = discord.utils.get(message.guild.roles, name=role_name)
                        if role and role not in message.author.roles:
                            try:
                                await message.author.add_roles(role)
                            except:  # noqa: E722
                                pass

    # --- Slash Commands ---

    @app_commands.command(
        name="rank",
        description="Check your current level and XP with a stylized image card",
    )
    @app_commands.guilds(GUILD_ID)
    async def rank(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Siden bildegenerering kan ta 1-2 sekunder

        user_id = interaction.user.id
        messages_sent, invite_xp = self.get_user_stats(user_id)
        current_xp = (messages_sent * XP_PER_MESSAGE) + invite_xp
        current_level = get_level_from_xp(current_xp)

        # Kalkuleringer for baren
        xp_needed_for_next = get_xp_for_level(current_level + 1)
        xp_achieved_in_prev = get_xp_for_level(current_level)

        # XP i *nåværende* nivå (fraction)
        xp_in_level = current_xp - xp_achieved_in_prev
        needed_in_level = xp_needed_for_next - xp_achieved_in_prev

        # Beregn Rank # (Posisjon) ved hjelp av cachen
        await self.update_leaderboard_cache()
        user_rank = "N/A"
        for i, user_data in enumerate(self.cached_ranks, start=1):
            if user_data["user_id"] == user_id:
                user_rank = i
                break

        # ==========================================
        # 🎨 EASY-PIL IMAGE GENERATION (THE CORE)
        # ==========================================

        # 1. Canvas og Bakgrunn (Sørg for at filen finnes!)
        try:
            background = Editor(BACKGROUND_IMAGE_PATH).resize((900, 250))
        except FileNotFoundError:
            logger.error(f"Missing background image at {BACKGROUND_IMAGE_PATH}")
            return await interaction.followup.send(
                "❌ Internal Error: Missing image asset."
            )

        # 2. Last og bearbeid profilbilde
        avatar_image = await load_image_async(str(interaction.user.display_avatar.url))
        avatar = Editor(avatar_image).resize((180, 180)).circle_image()

        # 3. Definer Fonts (Poppins er innebygd i easy-pil)
        # Bruker Regular variant, Bold for viktigere ting
        font_bold_lg = Font.poppins(size=50, variant="bold")
        font_medium = Font.poppins(size=35, variant="regular")
        font_small = Font.poppins(size=25, variant="regular")

        # 4. Farger (Hex koder)
        COLOR_WHITE = "#FFFFFF"
        COLOR_GREEN = "#00E676"  # En lys og klar grønn farge
        COLOR_BAR_BG = "#332A4A"  # Mørk lilla/grå for bakgrunnen på baren

        # 5. Tegn elementer på bakgrunnen

        # -- Profilbilde og outline --
        background.paste(avatar, (40, 35))  # x=40 (margin), y=35
        background.ellipse((40, 35), 180, 180, outline=COLOR_WHITE, stroke_width=4)

        # -- Brukernavn --
        # Justert for å matche stilen i eksempelet, til høyre for avatar
        # Bruker display_name for å unngå discriminators (#0000)
        background.text(
            (250, 80),  # Posisjon: x, y
            f"{interaction.user.display_name}",
            color=COLOR_WHITE,
            font=font_medium,
        )

        # -- Rank # og Level (Høyre hjørne) --
        # Vi flytter disse litt lenger inn fra kanten for margin
        # Level (1) [Hvit tekst, Bold]
        background.text(
            (850, 40),  # Posisjon helt til høyre, y=40
            f"LEVEL {current_level}",
            color=COLOR_WHITE,
            font=font_bold_lg,
            align="right",
        )

        # Rank #XXXX [Hvit tekst, Regular]
        # Justert x-posisjon for å stå til venstre for Level
        rank_text = f"RANK #{user_rank}"

        background.text(
            (630, 47),  # Posisjon litt til venstre for LEVEL, y=47 (litt lavere)
            rank_text,
            color=COLOR_WHITE,
            font=font_small,
            align="right",
        )

        # -- XP Bar og XP-tall --
        bar_x = 250
        bar_y = 150
        bar_width = 600
        bar_height = 40

        # Bakgrunnen på XP baren (mørk)
        background.rectangle(
            (bar_x, bar_y),
            bar_width,
            bar_height,
            fill=COLOR_BAR_BG,
            radius=20,  # Avrundede hjørner
        )

        # Fyllet på baren (Lys Grønn)
        progress = xp_in_level / needed_in_level if needed_in_level > 0 else 1
        filled_width = int(bar_width * progress)

        background.rectangle(
            (bar_x, bar_y),
            filled_width,
            bar_height,
            fill=COLOR_GREEN,
            radius=20,  # Avrundede hjørner
        )

        # XP Tallene (0 / 155 XP) [Hvit tekst, Regular]
        # Plassert til høyre over baren, under LEVEL-teksten
        xp_fraction_text = f"{xp_in_level:,} / {needed_in_level:,} XP"

        background.text(
            (
                850,
                bar_y - 35,
            ),  # X=850 sørger for at den flukter med baren og Level-teksten
            xp_fraction_text,
            color=COLOR_WHITE,
            font=font_small,
            align="right",  # Endret fra center til right
        )

        # ==========================================
        # 📤 SEND THE IMAGE
        # ==========================================

        # Oppretter filen i minnet (ikke lagrer den på disk)
        file = discord.File(fp=background.image_bytes, filename="rank_card.png")
        await interaction.followup.send(file=file)

    @app_commands.command(
        name="leaderboard", description="View the server's XP leaderboard"
    )
    @app_commands.guilds(GUILD_ID)
    async def leaderboard(self, interaction: discord.Interaction):
        all_users = []

        # Read all files in the data folder
        if os.path.exists(DATA_FOLDER):
            for filename in os.listdir(DATA_FOLDER):
                if filename.endswith(".json") and filename != "level_tracking.json":
                    try:
                        with open(os.path.join(DATA_FOLDER, filename), "r") as f:
                            data = json.load(f)
                            msgs = data.get("messages_sent", 0)
                            invite_xp = data.get("invite_xp", 0)
                            user_xp = msgs * XP_PER_MESSAGE + invite_xp
                            if user_xp > 0:
                                user_level = get_level_from_xp(user_xp)
                                all_users.append(
                                    {
                                        "user_id": data.get("user_id"),
                                        "xp": user_xp,
                                        "level": user_level,
                                    }
                                )
                    except Exception as e:
                        logger.error(f"Error reading {filename} for leaderboard: {e}")

        # Sort users by XP descending
        all_users.sort(key=lambda x: x["xp"], reverse=True)

        if not all_users:
            return await interaction.response.send_message(
                "No data available for the leaderboard yet!", ephemeral=True
            )

        view = LeaderboardView(data=all_users, user=interaction.user)
        embed = view.generate_embed()

        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingSystem(bot))
