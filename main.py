import discord
from discord.ext import commands
import os
import signal
import sys
import logging
import asyncio
from pathlib import Path

import config
from config import GUILD_ID as _GUILD_ID, Role

# Alle relative stier (./cogs, JSON-data, bilder) regnes fra prosjektmappen,
# så boten fungerer uansett hvilken mappe den startes fra.
os.chdir(Path(__file__).resolve().parent)

DISCORD_TOKEN = config.DISCORD_TOKEN
MINIGAME_DISCORD_TOKEN = config.MINIGAME_DISCORD_TOKEN

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

GUILD_ID = discord.Object(id=_GUILD_ID)

MEMBER_ROLE_ID = Role.MEMBER


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
        if os.path.isdir(full_path) and not filename.startswith("_"):
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
                except commands.NoEntryPointError:
                    # Hjelpemoduler (uten setup()) er ikke cogs — ikke en feil
                    logger.debug(f"Skipping helper module {module_name} (no setup()).")
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


def check_server_config():
    """Logger tydelig hvilke ID-er i server_config.toml / config.py som ikke stemmer."""
    guild = bot.get_guild(GUILD_ID.id)
    if guild is None:
        logger.warning(
            f"⚠️ The bot is not in guild {GUILD_ID.id} (guild_id in server_config.toml). "
            "Slash commands like /rank will not show up and most features won't work. "
            f"The bot is in: {', '.join(f'{g.name} ({g.id})' for g in bot.guilds) or 'no servers'}"
        )
        return
    problems = config.validate_guild(guild)
    if problems:
        logger.warning(
            f"⚠️ {len(problems)} configured ID(s) not found in '{guild.name}'. "
            "Features using them won't work — fix them in server_config.toml:\n  - "
            + "\n  - ".join(problems)
        )
    else:
        logger.info(f"✅ All configured channels and roles found in '{guild.name}'.")


_startup_done = False


@bot.event
async def on_ready():
    # on_ready kjøres på nytt ved hver reconnect — engangsoppsett gjøres bare første gang
    global _startup_done
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    if _startup_done:
        return
    _startup_done = True

    # Cogs som trenger oppsett etter at boten er klar
    tickets = bot.get_cog("Tickets")
    if tickets and hasattr(tickets, "on_ready_setup"):
        try:
            await tickets.on_ready_setup()
        except Exception:
            logger.exception("Error calling Tickets on_ready_setup")

    check_server_config()
    try:
        synced = await bot.tree.sync(guild=GUILD_ID)
        logger.info(f"Synced {len(synced)} commands to the guild {GUILD_ID.id}.")
    except Exception:
        logger.exception("Error syncing commands")


_minigame_synced = False


async def on_minigame_ready():
    global _minigame_synced
    logger.info(f"🎮 Minigame bot logged in as {minigame_bot.user} (ID: {minigame_bot.user.id})")
    if _minigame_synced:
        return
    _minigame_synced = True
    try:
        synced = await minigame_bot.tree.sync(guild=GUILD_ID)
        logger.info(f"Synced {len(synced)} minigame commands to guild {GUILD_ID.id}.")
    except Exception:
        logger.exception("Error syncing minigame commands")


minigame_bot.add_listener(on_minigame_ready, "on_ready")


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
    try:
        await minigame_bot.start(MINIGAME_DISCORD_TOKEN)
    except discord.LoginFailure:
        logger.error(
            "❌ Minigame bot: MINIGAME_DISCORD_TOKEN is invalid — mini-games are offline. "
            "The main bot keeps running."
        )
    except discord.PrivilegedIntentsRequired:
        logger.error(
            "❌ Minigame bot: enable Server Members and Message Content intents for the "
            "minigame app in the Developer Portal — mini-games are offline. The main bot keeps running."
        )
    except Exception:
        # Minigame-boten skal aldri ta ned hovedboten
        logger.exception("❌ Minigame bot crashed — mini-games are offline. The main bot keeps running.")
    finally:
        if not minigame_bot.is_closed():
            await minigame_bot.close()


async def shutdown(sig_name: str):
    """Ryddig avslutning: unload cogs (så de lagrer data i minnet) og lukk botene."""
    logger.info(f"Received {sig_name} — shutting down...")
    for target in (bot, minigame_bot):
        for ext in list(target.extensions):
            try:
                await target.unload_extension(ext)
            except Exception:
                logger.exception(f"Error unloading {ext}")
        if not target.is_closed():
            await target.close()


async def main():
    # systemctl stop sender SIGTERM; uten dette ville prosessen bare blitt drept
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s.name)))
        except NotImplementedError:
            pass  # Windows støtter ikke signal-handlere i asyncio
    await asyncio.gather(run_main_bot(), run_minigame_bot())


# --- Kjør boten ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and paste your bot token in it."
        )
        sys.exit(1)
    try:
        # Bruk asyncio.run for å starte boten
        asyncio.run(main())

    except discord.errors.LoginFailure:
        logger.error("Failed to log in. Check if your DISCORD_TOKEN is correct.")
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        logger.error(
            "Enable Server Members and Message Content intents for the bot in the "
            "Discord Developer Portal (Bot → Privileged Gateway Intents)."
        )
        sys.exit(1)
    except Exception:
        # Ikke-null exit-kode, så systemd (Restart=on-failure) starter boten på nytt
        logger.exception("An unexpected error occurred")
        sys.exit(1)
