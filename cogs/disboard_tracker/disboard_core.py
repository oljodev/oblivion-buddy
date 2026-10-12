from cogs._shared.json_store import load_json, save_json

DATA_FILE = "./cogs/disboard_tracker/disboard_data.json"


def load_data():
    data = load_json(DATA_FILE, {"bumps": [], "joins": []})

    # Sørg for at de forventede nøklene finnes (tilbakekompatibilitet).
    data.setdefault("bumps", [])
    data.setdefault("joins", [])
    return data


def save_data(data):
    save_json(DATA_FILE, data)
