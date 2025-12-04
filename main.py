import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import logging
import asyncio

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

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

GUILD_ID = discord.Object(id=1422932147550818507)

MEMBER_ROLE_ID = 1422937958897422406


@bot.event
async def on_member_join(member: discord.Member):
    role = member.guild.get_role(MEMBER_ROLE_ID)
    if role:
        try:
            await member.add_roles(role)
            logger.info(f"Assigned role {role.name} to {member.name}")
        except Exception as e:
            logger.error(f"Could not assign role: {e}")
    else:
        logger.warning("Role not found!")


@bot.tree.command(name="help", description="Shows how to use the bot.", guild=GUILD_ID)
async def help_command_for_users(interaction: discord.Interaction):
    help_text = (
        "Available commands:\n\n"
        "/stats <username> - Get simple Discord stats for a user\n"
        "!ai - Interact with the AI bot in ticket threads\n"
        "\nThanks for using our bot!"
    )
    await interaction.response.send_message(help_text)


async def load_cogs(bot: commands.Bot, logger: logging.Logger):
    cogs_path = "./cogs"

    # Sørg for at cogs-mappen eksisterer
    if not os.path.exists(cogs_path):
        logger.error(f"❌ Cogs folder not found at {cogs_path}")
        return

    for filename in os.listdir(cogs_path):
        full_path = os.path.join(cogs_path, filename)

        # --- 1. Sub-folders ---
        if os.path.isdir(full_path) and not filename.startswith("__"):
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
                    await bot.load_extension(module_name)
                    logger.info(f"✅ Loaded Cog (Sub-Module): {module_name}")
                except Exception as e:
                    logger.error(f"❌ Can't load package {module_name}. Error: {e}")

        # --- 2. Single .py files in cogs folder ---
        elif filename.endswith(".py") and not filename.startswith("__"):
            module_name = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(module_name)
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


async def main():
    await load_cogs(bot, logger)
    await bot.start(DISCORD_TOKEN)


# --- Kjør boten ---
if __name__ == "__main__":
    try:
        # Bruk asyncio.run for å starte boten
        asyncio.run(main())

    except discord.errors.LoginFailure:
        logger.error("Failed to log in. Check if your DISCORD_TOKEN is correct.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
