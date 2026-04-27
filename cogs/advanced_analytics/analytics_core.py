import json
import os
from datetime import datetime, timedelta

DATA_FILE = "./cogs/advanced_analytics/analytics.json"
RETENTION_DAYS = 30


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_data(data):
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


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
