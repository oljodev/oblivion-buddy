"""Shared helper: who is online on the Minecraft server, mapped to Discord.

Multiple cogs (playtime XP, daily login, future features) want the same
"who is online right now" info. We cache the RCON `list` result for 30s so
that simultaneous callers don't multiply RCON traffic.
"""

import asyncio
import logging
import os
import re
import time

from aiomcrcon import Client

from cogs.account_link.account_link import get_discord_id

logger = logging.getLogger("MCOnline")

RCON_IP = os.getenv("RCON_IP", "localhost")
RCON_PORT = int(os.getenv("RCON_PORT", 25575))
RCON_PASS = os.getenv("RCON_PASS", "secret")

CACHE_TTL_SECONDS = 30

MC_NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
LIST_NAMES_RE = re.compile(r"online:?\s*(.*)", re.IGNORECASE)

_BLACKLIST_NAMES = {
    "there", "are", "of", "max", "players", "online", "server", "info",
    "list", "connected", "joined", "left", "for", "get", "set", "value",
    "playtime", "none", "null", "the", "and", "from", "with", "have",
    "has", "was", "not", "out", "all", "any", "can", "cant", "true",
    "false", "error", "warn", "warning", "debug", "trigger", "scoreboard",
    "objective", "objectives", "score", "found", "unknown", "missing",
}

_cache_names: list[str] | None = None
_cache_at: float = 0.0
_lock = asyncio.Lock()


def _parse_names(text: str) -> list[str]:
    """Strict parser matching cogs/simple_stats/players_online.py."""
    if not text:
        return []
    m = LIST_NAMES_RE.search(text)
    if not m:
        return []
    raw = m.group(1)
    out = []
    for tok in re.split(r"[,\s]+", raw):
        clean = re.sub(r"^[^A-Za-z0-9_]+|[^A-Za-z0-9_]+$", "", tok)
        if not MC_NAME_RE.match(clean):
            continue
        if clean.lower() in _BLACKLIST_NAMES:
            continue
        if clean.isdigit():
            continue
        out.append(clean)
    # de-dupe preserving order
    seen = set()
    uniq = []
    for n in out:
        if n.lower() not in seen:
            seen.add(n.lower())
            uniq.append(n)
    return uniq


async def get_online_names(force_refresh: bool = False) -> list[str]:
    """Return the list of currently-online Minecraft usernames.

    Cached for CACHE_TTL_SECONDS. Returns [] on RCON failure.
    """
    global _cache_names, _cache_at
    async with _lock:
        if (
            not force_refresh
            and _cache_names is not None
            and (time.time() - _cache_at) < CACHE_TTL_SECONDS
        ):
            return list(_cache_names)
        try:
            async with Client(RCON_IP, RCON_PORT, RCON_PASS) as client:
                resp = await client.send_cmd("list")
            text = resp[0] if isinstance(resp, tuple) else str(resp)
            _cache_names = _parse_names(text)
            _cache_at = time.time()
            return list(_cache_names)
        except Exception as e:
            logger.debug(f"RCON list failed: {e}")
            # Don't poison the cache on failure — return empty but keep stale
            # cache for next caller (with stale TTL still valid).
            if _cache_names is not None and (time.time() - _cache_at) < CACHE_TTL_SECONDS:
                return list(_cache_names)
            return []


async def get_online_linked() -> list[tuple[int, str]]:
    """Return [(discord_id, mc_name), ...] for currently-online linked players."""
    names = await get_online_names()
    out = []
    for name in names:
        did = get_discord_id(name)
        if did is not None:
            out.append((did, name))
    return out
