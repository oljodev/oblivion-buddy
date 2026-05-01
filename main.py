import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import logging
import asyncio

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MINIGAME_DISCORD_TOKEN = os.getenv("MINIGAME_DISCORD_TOKEN")

# Cogs (sub-folder names) som skal kjøres på minigame-boten i stedet for hovedboten.
MINIGAME_COG_FOLDERS = {"mini_games"}

# --- Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- Bot Initialisering ---

# 1. Definer Intents riktig. Vi bruker Intents.default() og legger til de privilegerte vi trenger.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


bot = commands.Bot(command_prefix="!", intents=intents)
minigame_bot = commands.Bot(command_prefix="!", intents=intents)

GUILD_ID = discord.Object(id=1422932147550818507)

MEMBER_ROLE_ID = 1422937958897422406


@bot.event
async def on_member_join(member: discord.Member):
    # Sjekk om det er et menneske (ikke en bot)
    if not member.bot:
        role = member.guild.get_role(MEMBER_ROLE_ID)
        if role:
            try:
                await member.add_roles(role)
                logger.info(f"Assigned role {role.name} to human user: {member.name}")
            except Exception as e:
                logger.error(f"Could not assign role to {member.name}: {e}")
        else:
            logger.warning("Member role not found!")
    else:
        # Hvis det er en bot, logger vi det bare (denne fanges opp av Cogen vi laget i forrige svar)
        logger.info(f"App detected: {member.name}. Skipping auto-member role.")


@bot.tree.command(name="help", description="Shows how to use the bot.", guild=GUILD_ID)
async def help_command_for_users(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Oblivion Buddy — Help",
        description=(
            "Here's everything you can do with me. "
            "All commands are slash commands — just start typing `/` to see them in Discord."
        ),
        color=discord.Color.blurple(),
    )

    embed.add_field(
        name="🔗 Minecraft",
        value=(
            "**/link** — Link your Discord to your Minecraft account. "
            "Opens a panel with **Link**, **Unlink** and **Who am I?** buttons."
        ),
        inline=False,
    )

    embed.add_field(
        name="📈 Levels & Stats",
        value=(
            "**/rank** — Show your level and XP as a styled card.\n"
            "**/leaderboard** — See the server's XP leaderboard.\n"
            "**/stats** `<user>` — Look up Discord activity stats for a user."
        ),
        inline=False,
    )

    embed.add_field(
        name="🎮 Mini-games",
        value=(
            "**/trivia** — Start a 5-round Minecraft trivia game with escalating difficulty.\n"
            "**/minesweeper** — Launch the Oblivion Minesweeper Discord Activity."
        ),
        inline=False,
    )

    embed.add_field(
        name="❓ Other",
        value="**/help** — Show this message.",
        inline=False,
    )

    embed.set_footer(text="Tip: most replies are only visible to you.")

    await interaction.response.send_message(embed=embed, ephemeral=True)


async def load_cogs(
    target_bot: commands.Bot,
    logger: logging.Logger,
    *,
    folders: set[str] | None = None,
    exclude_folders: set[str] | None = None,
    include_top_level_files: bool = True,
):
    """Last cogs inn på en gitt bot.

    folders: hvis satt, bare last cogs fra disse undermappene.
    exclude_folders: hopp over disse undermappene.
    include_top_level_files: om enkeltfiler direkte i ./cogs skal lastes.
    """
    cogs_path = "./cogs"

    # Sørg for at cogs-mappen eksisterer
    if not os.path.exists(cogs_path):
        logger.error(f"❌ Cogs folder not found at {cogs_path}")
        return

    for filename in os.listdir(cogs_path):
        full_path = os.path.join(cogs_path, filename)

        # --- 1. Sub-folders ---
        if os.path.isdir(full_path) and not filename.startswith("__"):
            if folders is not None and filename not in folders:
                continue
            if exclude_folders is not None and filename in exclude_folders:
                continue

            # Sjekk alle .py filer i mappen
            py_files = [
                f
                for f in os.listdir(full_path)
                if f.endswith(".py") and not f.startswith("__")
            ]
            if not py_files:
                logger.warning(f"⚠️ Skipping folder '{filename}': no .py files found.")
                continue

            for py_file in py_files:
                module_name = f"cogs.{filename}.{py_file[:-3]}"
                try:
                    await target_bot.load_extension(module_name)
                    logger.info(f"✅ Loaded Cog (Sub-Module): {module_name}")
                except Exception as e:
                    logger.error(f"❌ Can't load package {module_name}. Error: {e}")

        # --- 2. Single .py files in cogs folder ---
        elif filename.endswith(".py") and not filename.startswith("__"):
            if not include_top_level_files:
                continue
            module_name = f"cogs.{filename[:-3]}"
            try:
                await target_bot.load_extension(module_name)
                logger.info(f"✅ Loaded Cog (File): {module_name}")
            except Exception as e:
                logger.error(f"❌ Can't load package {module_name}. Error: {e}")


@bot.event
async def on_ready():
    # Sørg for at boten er klar før vi logger
    await bot.wait_until_ready()
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    # 2. Kall opp setup-funksjonene i Cogs som må kjøres etter on_ready
    if bot.get_cog("Tickets"):
        try:
            # Sjekk om metoden finnes FØR vi kaller den
            if hasattr(bot.get_cog("Tickets"), "on_ready_setup"):
                await bot.get_cog("Tickets").on_ready_setup()
        except Exception as e:
            print(f"Error calling Tickets on_ready_setup: {e}")

    # 3. Sync kommandoer til en spesifikk guild (server)
    try:
        guild = discord.Object(id=1422932147550818507)
        # Bruk bot.tree.copy_global_to(guild=guild) hvis du har globale kommandoer du vil teste
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands to the guild {guild.id}.")

    except Exception as e:
        print(f"Error syncing commands: {e}")

    print("----------------------------------------------------")


@minigame_bot.event
async def on_ready():
    await minigame_bot.wait_until_ready()
    print(f"🎮 Minigame bot logged in as {minigame_bot.user} (ID: {minigame_bot.user.id})")
    try:
        synced = await minigame_bot.tree.sync(guild=GUILD_ID)
        print(f"Synced {len(synced)} minigame commands to guild {GUILD_ID.id}.")
    except Exception as e:
        print(f"Error syncing minigame commands: {e}")
    print("----------------------------------------------------")


async def run_main_bot():
    await load_cogs(bot, logger, exclude_folders=MINIGAME_COG_FOLDERS)
    await bot.start(DISCORD_TOKEN)


async def run_minigame_bot():
    if not MINIGAME_DISCORD_TOKEN:
        logger.warning("MINIGAME_DISCORD_TOKEN not set — skipping minigame bot.")
        return
    await load_cogs(
        minigame_bot,
        logger,
        folders=MINIGAME_COG_FOLDERS,
        include_top_level_files=False,
    )
    await minigame_bot.start(MINIGAME_DISCORD_TOKEN)


async def main():
    await asyncio.gather(run_main_bot(), run_minigame_bot())


# --- Kjør boten ---
if __name__ == "__main__":
    try:
        # Bruk asyncio.run for å starte boten
        asyncio.run(main())

    except discord.errors.LoginFailure:
        logger.error("Failed to log in. Check if your DISCORD_TOKEN is correct.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
