"""Pet companions: cosmetic sprite that replaces the avatar on /rank cards.

Players choose via /pets whether their rank card shows their Discord profile
picture or one of their unlocked pets — they cannot have both.

Every player gets a random starter pet on first interaction (granted lazily
the next time they post a message or open /pets). They then unlock one
additional pet per 5 levels (level 5, 10, ..., 100), so a brand-new player
sits with 1 pet through level 4 and ends up with 21 by level 100 — capped
by the size of the sprite pool.

State files
-----------
pets.json (committed):
    [
      {"id": 1, "name": "Fish", "unlock_level": 5, "file": "pet_01.png"},
      ...
    ]

  Auto-generated on first cog load if missing, by scanning the processed/
  directory. Names default to "Pet N"; the server admin can rename via the
  JSON file directly.

owned.json (runtime):
    {"<discord_id>": {"owned": [1, 2, 5], "active": 2, "starter_granted": true}}
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from config import GUILD_ID as _GUILD_ID, Role

logger = logging.getLogger("Pets")

GUILD_ID = discord.Object(id=_GUILD_ID)

PETS_DIR = Path(__file__).parent / "pets"
PROCESSED_DIR = PETS_DIR / "processed"
PETS_FILE = PETS_DIR / "pets.json"
OWNED_FILE = PETS_DIR / "owned.json"


# ---------- JSON helpers ----------


def _atomic_write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
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


# ---------- pets.json ----------


def _generate_default_metadata() -> list[dict]:
    """Scan processed/ directory and produce a metadata list."""
    if not PROCESSED_DIR.exists():
        return []
    entries = []
    for f in sorted(PROCESSED_DIR.glob("pet_*.png")):
        # Expect filenames like pet_01.png, pet_20.png.
        stem = f.stem  # pet_01
        try:
            num = int(stem.split("_", 1)[1])
        except (IndexError, ValueError):
            logger.warning(f"Skipping {f.name} — unexpected name pattern")
            continue
        entries.append(
            {
                "id": num,
                "name": f"Pet {num}",
                "unlock_level": num * 5,
                "file": f.name,
            }
        )
    return entries


def load_pets() -> list[dict]:
    """Load pet metadata, syncing newly-processed sprites into pets.json.

    On every call we union the existing pets.json (which may have admin-edited
    names) with anything new under processed/, so dropping a fresh sprite into
    that directory makes it appear without manual JSON editing.
    """
    existing = _load_json(PETS_FILE, []) if PETS_FILE.exists() else []
    existing_ids = {p["id"] for p in existing}
    discovered = _generate_default_metadata()
    new_entries = [p for p in discovered if p["id"] not in existing_ids]

    if not existing and not new_entries:
        return []

    if new_entries:
        merged = existing + new_entries
        try:
            _atomic_write(PETS_FILE, merged)
            logger.info(
                f"Synced pets.json: +{len(new_entries)} new, {len(existing)} existing"
            )
        except Exception as e:
            logger.error(f"Could not write pets.json: {e}")
        return merged
    return existing


def get_pet(pet_id: int) -> dict | None:
    for p in load_pets():
        if p["id"] == pet_id:
            return p
    return None


def get_pet_by_name(name: str) -> dict | None:
    target = name.lower().strip()
    for p in load_pets():
        if p["name"].lower() == target:
            return p
    return None


def pet_image_path(pet: dict) -> Path:
    return PROCESSED_DIR / pet["file"]


# ---------- DEV-team override ----------


def is_dev(user: discord.abc.User) -> bool:
    """DEV team members get unrestricted access to every pet for testing."""
    roles = getattr(user, "roles", None)
    if not roles:
        return False
    return any(r.id == Role.DEV_TEAM for r in roles)


def effective_owned_pets(user: discord.abc.User) -> list[dict]:
    """Pets the user is allowed to use — the full catalogue for DEV team."""
    if is_dev(user):
        return load_pets()
    return get_owned_pets(user.id)


# ---------- owned.json ----------


def _load_owned() -> dict:
    return _load_json(OWNED_FILE, {})


def _save_owned(data: dict):
    try:
        _atomic_write(OWNED_FILE, data)
    except Exception as e:
        logger.error(f"Failed to save owned.json: {e}")


def get_user_record(discord_id: int) -> dict:
    data = _load_owned()
    rec = data.get(str(discord_id), {"owned": [], "active": None, "starter_granted": False})
    rec.setdefault("owned", [])
    rec.setdefault("active", None)
    rec.setdefault("starter_granted", False)
    return rec


def get_owned_pets(discord_id: int) -> list[dict]:
    rec = get_user_record(discord_id)
    return [p for pet_id in rec["owned"] if (p := get_pet(pet_id)) is not None]


def get_active_pet(discord_id: int) -> dict | None:
    rec = get_user_record(discord_id)
    if rec["active"] is None:
        return None
    return get_pet(rec["active"])


def set_active(discord_id: int, pet_id: int | None):
    data = _load_owned()
    rec = data.get(str(discord_id), {"owned": [], "active": None})
    rec["active"] = pet_id
    data[str(discord_id)] = rec
    _save_owned(data)


def backfill_pets_up_to_level(discord_id: int, current_level: int) -> list[dict]:
    """Grant any missing pets for tiers the user has already passed.

    Used when a player was already past a milestone before the pets feature
    existed (or for any other reason their on_message grant was missed).
    Also grants the starter pet on first run. Returns the list of
    newly-granted pets.
    """
    granted: list[dict] = []
    starter = grant_starter_pet(discord_id)
    if starter is not None:
        granted.append(starter)
    for tier in range(5, min(current_level, 100) + 1, 5):
        pet = grant_pet_for_level(discord_id, tier)
        if pet is not None:
            granted.append(pet)
    return granted


def grant_starter_pet(discord_id: int) -> dict | None:
    """Grant a single random pet to any user who hasn't received their starter.

    Idempotent: a `starter_granted` flag is written so this is a no-op on
    subsequent calls. Existing users who already claimed level-milestone pets
    will get one *additional* random pet they don't already own — that pet
    becomes their starter so the totals stay consistent (pets owned =
    1 + completed_5lvl_milestones).
    """
    data = _load_owned()
    rec = data.get(
        str(discord_id), {"owned": [], "active": None, "starter_granted": False}
    )
    if rec.get("starter_granted"):
        return None
    all_pets = load_pets()
    if not all_pets:
        return None
    owned_set = set(rec.get("owned", []))
    available = [p for p in all_pets if p["id"] not in owned_set]
    if not available:
        # All pets already owned — flag the starter as granted so we don't keep
        # re-checking on every message.
        rec["starter_granted"] = True
        data[str(discord_id)] = rec
        _save_owned(data)
        return None
    chosen = random.choice(available)
    rec["owned"] = sorted(owned_set | {chosen["id"]})
    if rec.get("active") is None:
        rec["active"] = chosen["id"]
    rec["starter_granted"] = True
    data[str(discord_id)] = rec
    _save_owned(data)
    return chosen


def grant_pet_for_level(discord_id: int, level: int) -> dict | None:
    """At every 5th level (≤ 100), grant one random pet from the unowned pool.

    Pet selection is independent of which milestone triggered it — two players
    crossing level 5 may unlock different pets, which gives the collection
    real variation.
    """
    if level <= 0 or level > 100 or level % 5 != 0:
        return None
    all_pets = load_pets()
    if not all_pets:
        return None

    data = _load_owned()
    rec = data.get(str(discord_id), {"owned": [], "active": None})
    owned_set = set(rec["owned"])
    available = [p for p in all_pets if p["id"] not in owned_set]
    if not available:
        return None
    chosen = random.choice(available)
    rec["owned"] = sorted(owned_set | {chosen["id"]})
    if rec["active"] is None:
        rec["active"] = chosen["id"]
    data[str(discord_id)] = rec
    _save_owned(data)
    return chosen


# ---------- Slash command + UI ----------


def _build_pets_embed(user: discord.abc.User) -> tuple[discord.Embed, discord.File | None]:
    available = effective_owned_pets(user)
    active = get_active_pet(user.id)
    all_pets = load_pets()
    dev = is_dev(user)

    available_ids = {p["id"] for p in available}
    lines = []
    for pet in sorted(all_pets, key=lambda p: p["unlock_level"]):
        if pet["id"] in available_ids:
            marker = "🟢" if active and active["id"] == pet["id"] else "⚪"
            lines.append(f"{marker} **{pet['name']}**")
        else:
            lines.append(f"🔒 *{pet['name']}* — random unlock at every 5 levels")

    intro = (
        "Pick a pet below to use it as your rank-card avatar, "
        "or switch back to your profile picture."
    )
    if dev:
        intro += "\n*(DEV access: all pets unlocked for testing.)*"

    embed = discord.Embed(
        title="🐾 Your pets",
        description=intro + "\n\n"
        + ("\n".join(lines) if lines else "No pets are set up on this server yet."),
        color=discord.Color.purple(),
    )

    file = None
    if active:
        sprite_path = pet_image_path(active)
        if sprite_path.exists():
            file = discord.File(sprite_path, filename=active["file"])
            embed.set_thumbnail(url=f"attachment://{active['file']}")
        embed.set_footer(text=f"Rank-card avatar: {active['name']}")
    else:
        embed.set_footer(text="Rank-card avatar: your profile picture")
    return embed, file


class PetSelect(discord.ui.Select):
    def __init__(self, user: discord.abc.User):
        available = effective_owned_pets(user)
        active = get_active_pet(user.id)
        active_id = active["id"] if active else None
        options = [
            discord.SelectOption(
                label=p["name"],
                value=str(p["id"]),
                default=(p["id"] == active_id),
            )
            for p in sorted(available, key=lambda x: x["unlock_level"])[:25]
        ]
        super().__init__(
            placeholder="Choose your active pet…" if options else "No pets unlocked yet",
            min_values=1,
            max_values=1,
            options=options or [discord.SelectOption(label="(none)", value="_none")],
            disabled=not options,
            row=0,
        )
        self.user_id = user.id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This menu isn't yours.", ephemeral=True
            )
        choice = self.values[0]
        if choice == "_none":
            return await interaction.response.defer()
        pet_id = int(choice)
        available_ids = {p["id"] for p in effective_owned_pets(interaction.user)}
        if pet_id not in available_ids:
            return await interaction.response.send_message(
                "🔒 You don't own that pet.", ephemeral=True
            )
        set_active(self.user_id, pet_id)
        embed, file = _build_pets_embed(interaction.user)
        view = PetsView(interaction.user)
        if file is not None:
            await interaction.response.edit_message(embed=embed, view=view, attachments=[file])
        else:
            await interaction.response.edit_message(embed=embed, view=view, attachments=[])


class HidePetButton(discord.ui.Button):
    def __init__(self, user_id: int, has_active: bool):
        super().__init__(
            label="Use profile picture",
            style=discord.ButtonStyle.secondary,
            emoji="👤",
            disabled=not has_active,
            row=1,
        )
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This menu isn't yours.", ephemeral=True
            )
        set_active(self.user_id, None)
        embed, file = _build_pets_embed(interaction.user)
        view = PetsView(interaction.user)
        if file is not None:
            await interaction.response.edit_message(embed=embed, view=view, attachments=[file])
        else:
            await interaction.response.edit_message(embed=embed, view=view, attachments=[])


class PetsView(discord.ui.View):
    def __init__(self, user: discord.abc.User):
        super().__init__(timeout=180)
        self.add_item(PetSelect(user))
        self.add_item(HidePetButton(user.id, has_active=get_active_pet(user.id) is not None))


class PetsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="pets",
        description="View your pet collection and pick which one shows on your rank card.",
    )
    @app_commands.guilds(GUILD_ID)
    async def pets(self, interaction: discord.Interaction):
        if not load_pets():
            return await interaction.response.send_message(
                "Pets aren't set up on this server yet — no sprites have been processed.",
                ephemeral=True,
            )

        # Backfill: grant any pets the user qualifies for but didn't receive
        # (e.g. they were already past the milestone before pets shipped).
        from cogs._shared import xp_store
        from cogs.leveling_system.leveling import get_level_from_xp

        current_level = get_level_from_xp(
            xp_store.get_total_xp(xp_store.get_user_stats(interaction.user.id))
        )
        backfill_pets_up_to_level(interaction.user.id, current_level)

        embed, file = _build_pets_embed(interaction.user)
        view = PetsView(interaction.user)
        if file is not None:
            await interaction.response.send_message(
                embed=embed, view=view, file=file, ephemeral=True
            )
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PetsCog(bot))
