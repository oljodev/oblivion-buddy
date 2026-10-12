"""Central configuration.

Secrets (tokens, passwords, API keys) come from `.env` — see `.env.example`.

Discord IDs (guild, channels, roles) default to the Oblivion SMP server below.
To run the bot in another server, copy `server_config.example.toml` to
`server_config.toml` and fill in your own IDs. Anything you leave out keeps the
default. The bot logs every channel/role it can't find on startup.
"""

import logging
import os
import sys
import tomllib
from enum import IntEnum
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("Config")

BASE_DIR = Path(__file__).resolve().parent
SERVER_CONFIG_FILE = BASE_DIR / "server_config.toml"

load_dotenv(BASE_DIR / ".env")


# ==========================================
# 🔑 SECRETS / CONNECTION SETTINGS (.env)
# ==========================================


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(f"{name}={raw!r} in .env is not a number — using {default}.")
        return default


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or None
MINIGAME_DISCORD_TOKEN = os.getenv("MINIGAME_DISCORD_TOKEN") or None

RCON_IP = os.getenv("RCON_IP") or "localhost"
RCON_PORT = _env_int("RCON_PORT", 25575)
RCON_PASS = os.getenv("RCON_PASS") or "secret"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or None
CURSEFORGE_API_KEY = os.getenv("CURSEFORGE_API_KEY") or None


# ==========================================
# 🆔 DISCORD IDS (defaults = Oblivion SMP)
# ==========================================

_DEFAULT_SERVER = {
    "guild_id": 1422932147550818507,
    # Discord Activity-app for /minesweeper
    "minesweeper_app_id": 1498035754566160454,
    # CurseForge-modpakken som sjekkes for oppdateringer (0 = av)
    "curseforge_modpack_id": 1356927,
}

_DEFAULT_CHANNELS = {
    # Welcome category
    "WELCOME": 1422933181497086122,
    "RULES": 1422935054501285961,
    "HOW_TO_JOIN": 1429884449667158026,
    # Important category
    "ANNOUNCEMENTS": 1422939665542942791,
    "UPDATES": 1422939796900282501,
    "GIVEAWAYS_AND_POLLS": 1422936288507461653,
    "TICKET": 1422936354404302921,
    # Community category
    "GENERAL": 1422934261983346751,
    "SHOWCASE": 1422934437813027040,
    "MEMES": 1422936504740610140,
    "BOT_COMMANDS": 1467529230966460448,
    "STATUS": 1422934996976402442,
    "MC_CHAT": 1442939418821529600,
    "SHOPS": 1422950500051058830,
    "SUGGESTIONS": 1435357404073033909,
    # Voice channels
    "GENERAL_VOICE": 1422939363100065912,
    "EVENTS_VOICE": 1452295182950207488,
    # Staff only category
    "STAFF_CHAT": 1451979797252276368,
    "NORWEGIAN_STAFF": 1422935303848726648,
    "MODERATION": 1435357010500780052,
    "BOT_STAFF": 1435347662982352926,
    "LINKS": 1442874380689477774,
    "FEATURES": 1449879191515566211,
    "NOTES": 1489681383201833283,
    # Server stats (staff only) category
    "SIMPLE_STATS": 1433549179942338570,
    "ADVANCED_STATS": 1452612533490946088,
    "LOG": 1452598796377653331,
}

_DEFAULT_ROLES = {
    "OWNER": 1422933406873813254,
    "ADMIN": 1422937935988265090,
    "HELPER": 1422937956959785040,
    "DEV_TEAM": 1449071882770055270,
    "MEMBER": 1422937958897422406,
    "GIVEAWAY_STAFF": 1478824797378187507,
    "BOT": 1422937956079112232,
    "CONNECTED_ACCOUNT": 1502733489491935334,
}


def _fail(msg: str):
    # Logging er ikke satt opp ennå når config importeres, så vi skriver rett til stderr
    print(f"❌ {SERVER_CONFIG_FILE.name}: {msg}", file=sys.stderr)
    sys.exit(1)


def _merge(section: str, defaults: dict, overrides: dict, upper: bool) -> dict:
    merged = dict(defaults)
    for key, value in overrides.items():
        name = key.upper() if upper else key.lower()
        if name not in defaults:
            _fail(f"unknown key '{key}' in [{section}]. Valid keys: {', '.join(k.lower() for k in defaults)}")
        if isinstance(value, bool) or not isinstance(value, int):
            _fail(f"[{section}] {key} must be a number (no quotes), got {value!r}")
        merged[name] = value
    return merged


def _load_server_config():
    if not SERVER_CONFIG_FILE.exists():
        return _DEFAULT_SERVER, _DEFAULT_CHANNELS, _DEFAULT_ROLES
    try:
        with SERVER_CONFIG_FILE.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        _fail(f"invalid TOML: {e}")
    unknown = set(data) - {"server", "channels", "roles"}
    if unknown:
        _fail(f"unknown section(s) {sorted(unknown)}. Use [server], [channels] and [roles].")
    return (
        _merge("server", _DEFAULT_SERVER, data.get("server", {}), upper=False),
        _merge("channels", _DEFAULT_CHANNELS, data.get("channels", {}), upper=True),
        _merge("roles", _DEFAULT_ROLES, data.get("roles", {}), upper=True),
    )


_server, _channels, _roles = _load_server_config()

GUILD_ID = _server["guild_id"]
MINESWEEPER_APP_ID = _server["minesweeper_app_id"]
CURSEFORGE_MODPACK_ID = _server["curseforge_modpack_id"]

Channel = IntEnum("Channel", _channels)
Role = IntEnum("Role", _roles)


def validate_guild(guild) -> list[str]:
    """Returns a list of human-readable problems with the configured IDs for `guild`."""
    problems = []
    # __members__ tar med alias, så flere kanaler/roller med samme ID (f.eks. 0) listes hver for seg
    for kind, enum, lookup in (("channel", Channel, guild.get_channel), ("role", Role, guild.get_role)):
        for name, member in enum.__members__.items():
            if member.value == 0:
                problems.append(f"{kind} {name.lower()} is not set (0)")
            elif lookup(member.value) is None:
                problems.append(f"{kind} {name.lower()} = {member.value} not found")
    return problems
