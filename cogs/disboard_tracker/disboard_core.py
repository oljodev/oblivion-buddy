import json
import os

DATA_FILE = "./cogs/disboard_tracker/disboard_data.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"bumps": [], "joins": []}
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"bumps": [], "joins": []}

    # Sørg for at de forventede nøklene finnes (tilbakekompatibilitet).
    data.setdefault("bumps", [])
    data.setdefault("joins", [])
    return data


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    # Atomisk skriv via temp-fil for å unngå korrupte JSON-filer ved krasj.
    tmp_path = DATA_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, DATA_FILE)
