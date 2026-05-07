"""Award XP when a linked player earns a Minecraft advancement.

A server-side mod authenticates with the bot's token and posts messages
into #mc-chat. Format observed:

    <MC_NAME> has made the advancement
    <TITLE>
    <italic description>

We listen for our own bot's messages in MC_CHAT, parse the player + title,
look up their Discord ID via the account-link helper, and award XP. Awarded
(discord_id, title) pairs are persisted to prevent double-counting if Discord
re-delivers the message.

The exact format from the mod isn't documented here, so the first time an
unrecognised message lands in MC_CHAT we log the raw payload to help refine
the parser.
"""

import json
import logging
import re
from pathlib import Path

import discord
from discord.ext import commands

from config import Channel
from cogs.account_link.account_link import get_discord_id
from cogs._shared import dev_mode, xp_store

logger = logging.getLogger("AchievementXP")

MC_CHAT_ID = int(Channel.MC_CHAT)

NORMAL_XP = 50
CHALLENGE_XP = 250

# Title substrings (case-insensitive) that mark a "challenge" / hard advancement.
# Extend as needed — vanilla "Goal" advancements aren't currently boosted; only
# the explicit challenge list below.
CHALLENGE_TITLES = {
    "how did we get here?",
    "monsters hunted",
    "a balanced diet",
    "two by two",
    "adventuring time",
    "beaconator",
    "the end... again...",
    "hero of the village",
    "sniper duel",
    "bullseye",
    "uneasy alliance",
    "subspace bubble",
    "a complete catalogue",
    "wax on",
    "wax off",
}

AWARDED_FILE = Path(__file__).parent / "awarded.json"

ADVANCEMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_]{3,16}) has made the advancement\b\s*(?P<title>.*)$",
    re.IGNORECASE,
)


def _atomic_write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _load_awarded() -> dict:
    if not AWARDED_FILE.exists():
        return {}
    try:
        with AWARDED_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load awarded.json: {e}")
        return {}


def _save_awarded(data: dict):
    try:
        _atomic_write(AWARDED_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save awarded.json: {e}")


def _parse_message(message: discord.Message) -> tuple[str, str] | None:
    """Try to extract (mc_name, advancement_title) from the message.

    Falls back through plain content, then embed title/description, since
    we don't yet know the mod's exact format.
    """
    candidates: list[str] = []
    if message.content:
        candidates.extend(line.strip() for line in message.content.splitlines() if line.strip())
    for emb in message.embeds:
        if emb.title:
            candidates.append(emb.title.strip())
        if emb.description:
            candidates.extend(
                line.strip() for line in emb.description.splitlines() if line.strip()
            )

    for line in candidates:
        m = ADVANCEMENT_RE.match(line)
        if m:
            name = m.group("name")
            title = (m.group("title") or "").strip()
            # If the regex captured an empty title, the title may be on the next
            # candidate line (multi-line format).
            if not title:
                idx = candidates.index(line)
                if idx + 1 < len(candidates):
                    title = candidates[idx + 1].strip()
            return name, title or "(unknown)"
    return None


def _xp_for_title(title: str) -> int:
    return CHALLENGE_XP if title.lower().strip() in CHALLENGE_TITLES else NORMAL_XP


class AchievementXP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.awarded = _load_awarded()
        self._logged_unrecognised = False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != MC_CHAT_ID:
            return
        # Only react to our own bot's messages — that's how the server-side
        # mod posts achievements (it uses the bot token).
        if not self.bot.user or message.author.id != self.bot.user.id:
            return

        parsed = _parse_message(message)
        if not parsed:
            if not self._logged_unrecognised:
                self._logged_unrecognised = True
                logger.info(
                    f"Unrecognised MC_CHAT bot message (logging once to help refine parser): "
                    f"content={message.content!r} embeds={[e.to_dict() for e in message.embeds]}"
                )
            return

        mc_name, title = parsed
        discord_id = get_discord_id(mc_name)
        if discord_id is None:
            logger.debug(f"Advancement {title!r} from unlinked player {mc_name}")
            return
        if not dev_mode.is_eligible_id(self.bot, discord_id):
            return

        key = str(discord_id)
        already = set(self.awarded.get(key, []))
        title_norm = title.lower().strip()
        if title_norm in already:
            return  # idempotent

        xp = _xp_for_title(title)
        try:
            await xp_store.add_xp(discord_id, "achievement_xp", xp)
        except Exception as e:
            logger.error(f"Failed to add achievement XP for {discord_id}: {e}")
            return

        already.add(title_norm)
        self.awarded[key] = sorted(already)
        _save_awarded(self.awarded)
        logger.info(
            f"Achievement XP +{xp} to discord={discord_id} mc={mc_name} title={title!r}"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AchievementXP(bot))
