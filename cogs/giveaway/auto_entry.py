"""Helpers for the giveaway auto-entry mode.

Auto-entry mode qualifies a member if they:
  1. Have linked their Minecraft account (cogs/account_link/links.json), AND
  2. Have played >= 1 hour on the SMP in the last 7 days.

Total playtime is tracked by the Minecraft scoreboard objective `playtime`
(unit: ticks; 20 ticks = 1 second). To compute "last 7 days" we record
periodic snapshots and diff against the oldest snapshot inside the window.

Cold start: if no snapshot >=7 days old exists for a user, the oldest
snapshot we do have is used as the baseline.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiomcrcon import Client

logger = logging.getLogger("GiveawayAutoEntry")

from config import RCON_IP, RCON_PORT, RCON_PASS

LINKS_FILE = Path(__file__).parent.parent / "account_link" / "links.json"
SNAPSHOTS_FILE = Path(__file__).parent / "playtime_snapshots.json"

PLAYTIME_OBJECTIVE = "playtime"
SCORE_GET_RE = re.compile(r"\bhas\s+(-?\d+)\b", re.IGNORECASE)

WINDOW_DAYS = 7
RETENTION_DAYS = 8
REQUIRED_SECONDS = 60 * 60  # 1 hour
TICKS_PER_SEC = 20
REQUIRED_TICKS = REQUIRED_SECONDS * TICKS_PER_SEC


def _atomic_write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {path.name}: {e}")
        return default


def parse_role_field(value: str):
    """Parse the 'Required Role (Optional)' modal field.

    Returns (auto_mode: bool, role_query: str | None).

    Examples:
      ""              -> (False, None)
      "Member"        -> (False, "Member")
      "12345"         -> (False, "12345")
      "auto"          -> (True, None)
      "auto + Member" -> (True, "Member")
      "Member + auto" -> (True, "Member")
    """
    s = (value or "").strip()
    if not s:
        return False, None
    parts = [p.strip() for p in s.split("+")]
    auto_mode = False
    role_parts = []
    for p in parts:
        if p.lower() == "auto":
            auto_mode = True
        elif p:
            role_parts.append(p)
    role_query = " + ".join(role_parts) if role_parts else None
    return auto_mode, role_query


def get_mc_name(discord_id: int) -> str | None:
    links = _load_json(LINKS_FILE, {})
    info = links.get(str(discord_id))
    return info.get("mc_name") if info else None


async def query_playtime_ticks(mc_name: str) -> int | None:
    try:
        async with Client(RCON_IP, RCON_PORT, RCON_PASS) as client:
            response = await client.send_cmd(
                f"scoreboard players get {mc_name} {PLAYTIME_OBJECTIVE}"
            )
        text = response[0] if isinstance(response, tuple) else response
        m = SCORE_GET_RE.search(text)
        return int(m.group(1)) if m else None
    except Exception as e:
        logger.warning(f"RCON playtime query failed for {mc_name}: {e}")
        return None


def _load_snapshots() -> dict:
    return _load_json(SNAPSHOTS_FILE, {})


def _save_snapshots(data: dict):
    try:
        _atomic_write(SNAPSHOTS_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save playtime_snapshots.json: {e}")


def record_snapshot(discord_id: int, ticks: int, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    data = _load_snapshots()
    key = str(discord_id)
    entries = data.get(key, [])
    entries.append({"ts": now.isoformat(), "ticks": ticks})
    cutoff = now - timedelta(days=RETENTION_DAYS)
    entries = [
        e for e in entries
        if _safe_parse_ts(e.get("ts")) and _safe_parse_ts(e["ts"]) >= cutoff
    ]
    data[key] = entries
    _save_snapshots(data)


def _safe_parse_ts(s) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def seconds_in_window(
    discord_id: int, current_ticks: int, window_days: int = WINDOW_DAYS
) -> int:
    """Seconds played in the last `window_days` for a user.

    Cold-start rule: if our oldest snapshot is younger than the window, we
    cannot honestly measure "last N days" — playtime older than that snapshot
    is invisible to us. In that case we credit the full current cumulative
    playtime. Once we have a snapshot >= window_days old, strict measurement
    (current - oldest_in_window) takes over.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    entries = _load_snapshots().get(str(discord_id), [])
    parsed = []
    for e in entries:
        ts = _safe_parse_ts(e.get("ts"))
        if ts is not None and "ticks" in e:
            parsed.append((ts, int(e["ticks"])))
    if not parsed:
        return max(0, current_ticks) // TICKS_PER_SEC
    parsed.sort()
    oldest_ts = parsed[0][0]
    if oldest_ts > cutoff:
        # Cold start: no snapshot old enough to anchor the window.
        return max(0, current_ticks) // TICKS_PER_SEC
    in_window = [(t, ticks) for t, ticks in parsed if t >= cutoff]
    baseline_ticks = in_window[0][1] if in_window else parsed[0][1]
    diff_ticks = max(0, current_ticks - baseline_ticks)
    return diff_ticks // TICKS_PER_SEC


async def evaluate_user(
    discord_id: int,
    required_seconds: int = REQUIRED_SECONDS,
    window_days: int = WINDOW_DAYS,
) -> dict:
    """Live evaluation of a user's auto-entry qualification.

    Returns: {
      "linked": bool,
      "mc_name": str | None,
      "current_ticks": int | None,
      "seconds_in_window": int,
      "qualifies": bool,
    }
    """
    mc_name = get_mc_name(discord_id)
    if not mc_name:
        return {
            "linked": False, "mc_name": None, "current_ticks": None,
            "seconds_in_window": 0, "qualifies": False,
        }
    current_ticks = await query_playtime_ticks(mc_name)
    if current_ticks is None:
        return {
            "linked": True, "mc_name": mc_name, "current_ticks": None,
            "seconds_in_window": 0, "qualifies": False,
        }
    # Compute first against existing snapshots, then record. Otherwise the
    # snapshot we just took becomes its own baseline and the diff is zero.
    secs = seconds_in_window(discord_id, current_ticks, window_days=window_days)
    record_snapshot(discord_id, current_ticks)
    return {
        "linked": True, "mc_name": mc_name, "current_ticks": current_ticks,
        "seconds_in_window": secs, "qualifies": secs >= required_seconds,
    }


async def snapshot_all_linked() -> int:
    """Take a snapshot for every linked user. Returns count of successful records."""
    links = _load_json(LINKS_FILE, {})
    successes = 0
    for did_str, info in links.items():
        mc_name = info.get("mc_name") if isinstance(info, dict) else None
        if not mc_name:
            continue
        ticks = await query_playtime_ticks(mc_name)
        if ticks is None:
            continue
        try:
            record_snapshot(int(did_str), ticks)
            successes += 1
        except Exception as e:
            logger.error(f"Snapshot failed for {did_str}: {e}")
    return successes
