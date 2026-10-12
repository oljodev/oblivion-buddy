import atexit
import logging
from datetime import datetime, timedelta

from cogs._shared.json_store import load_json, save_json

DATA_FILE = "./cogs/advanced_analytics/analytics.json"
RETENTION_DAYS = 30


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


logger = logging.getLogger("Analytics")

# Analysedataene holdes i minnet: alle cogs deler samme dict, så ingen
# overskriver hverandres endringer. save_data() markerer bare endringer, og
# flush() skriver til disk (kalles hvert 30. sekund av DataCollector, ved
# unload og ved avslutning). Slik slipper vi å lese+skrive hele fila per melding.
_data: dict | None = None
_dirty = False


def load_data():
    global _data
    if _data is None:
        _data = load_json(DATA_FILE, {})
    return _data


def save_data(data=None):
    """Marker data som endret. Skrives til disk ved neste flush()."""
    global _data, _dirty
    if data is not None:
        _data = data
    _dirty = True


def flush():
    """Skriv endringer til disk hvis det finnes noen."""
    global _dirty
    if not _dirty or _data is None:
        return
    try:
        save_json(DATA_FILE, _data, indent=4)
        _dirty = False
    except Exception as e:
        logger.error(f"Failed to save analytics: {e}")


atexit.register(flush)


def prune_old_days(data):
    """Drop day entries older than RETENTION_DAYS. Keys not matching a date are kept."""
    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS - 1)).strftime("%Y-%m-%d")
    changed = False
    for key in list(data.keys()):
        if len(key) == 10 and key[0].isdigit() and key < cutoff:
            del data[key]
            changed = True
    return changed


def ensure_today_exists():
    data = load_data()
    today = get_today_str()

    pruned = prune_old_days(data)

    if today not in data:
        data[today] = {
            "discord": {
                "total_messages": 0,
                "joins": 0,
                "voice_minutes": 0,
                "unique_chatters": {},  # format: {"user_id": msg_count}
            },
            "minecraft": {
                "peak_players": 0,
                "unique_logins": [],  # list of player names
                "total_playtime_checks": 0,  # increments every 15 mins per player
                "active_slots": 0,  # 15-min polls where at least 1 player was online
            },
        }
        save_data(data)
    elif pruned:
        save_data(data)
    return data
