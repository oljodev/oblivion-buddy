import discord
from discord.ext import commands, tasks
from discord import app_commands
from aiomcrcon import Client
from pathlib import Path
import json
import random
import re
import time
import logging

from config import GUILD_ID as _GUILD_ID

logger = logging.getLogger("AccountLink")

GUILD_ID = discord.Object(id=_GUILD_ID)

from config import RCON_IP, RCON_PORT, RCON_PASS

OBJECTIVE = "link_code"
CODE_TTL_SECONDS = 5 * 60
POLL_INTERVAL_SECONDS = 5

PENDING_FILE = Path(__file__).parent / "pending.json"
LINKS_FILE = Path(__file__).parent / "links.json"

# RCON response patterns
SCORE_GET_RE = re.compile(r"\bhas\s+(-?\d+)\b", re.IGNORECASE)
# `list` response, e.g. "There are 2 of a max of 20 players online: kruk02, steve"
LIST_NAMES_RE = re.compile(r"online:?\s*(.*)", re.IGNORECASE)
MC_NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


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


def get_mc_name(discord_id: int) -> str | None:
    """Module-level helper: look up the linked Minecraft name for a Discord user."""
    links = _load_json(LINKS_FILE, {})
    info = links.get(str(discord_id))
    return info.get("mc_name") if info else None


def get_discord_id(mc_name: str) -> int | None:
    """Module-level helper: reverse lookup Discord ID from a Minecraft name."""
    links = _load_json(LINKS_FILE, {})
    target = mc_name.lower()
    for discord_id_str, info in links.items():
        if info.get("mc_name", "").lower() == target:
            try:
                return int(discord_id_str)
            except ValueError:
                return None
    return None


class AccountLink(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # pending: {code: {"discord_id": int, "mc_name": str, "expires_at": float}}
        self.pending: dict = _load_json(PENDING_FILE, {})
        # links: {discord_id_str: {"mc_name": str, "linked_at": float}}
        self.links: dict = _load_json(LINKS_FILE, {})
        self._objective_ready = False
        self.poll_pending.start()

    def cog_unload(self):
        self.poll_pending.cancel()

    # --- RCON helper ---
    async def _rcon(self, command: str) -> str:
        async with Client(RCON_IP, RCON_PORT, RCON_PASS) as client:
            response = await client.send_cmd(command)
        return response[0] if isinstance(response, tuple) else response

    async def _ensure_objective(self):
        if self._objective_ready:
            return
        try:
            # Idempotent: if it exists, this just returns an error string we ignore.
            await self._rcon(f"scoreboard objectives add {OBJECTIVE} trigger")
        except Exception as e:
            logger.warning(f"Could not ensure objective: {e}")
            return
        self._objective_ready = True

    # --- Persistence ---
    def _save_pending(self):
        _atomic_write(PENDING_FILE, self.pending)

    def _save_links(self):
        _atomic_write(LINKS_FILE, self.links)

    # --- UI helpers ---
    def _build_status_embed(self, user: discord.abc.User) -> discord.Embed:
        info = self.links.get(str(user.id))
        pending_for_user = [
            (code, p)
            for code, p in self.pending.items()
            if p["discord_id"] == user.id and p["expires_at"] > time.time()
        ]

        if info:
            embed = discord.Embed(
                title="🔗 Minecraft Account Link",
                description=f"You are linked to **{info['mc_name']}**.",
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="🔗 Minecraft Account Link",
                description=(
                    "Your Discord is **not** linked to a Minecraft account yet.\n\n"
                    "Press **Link** to start the process."
                ),
                color=discord.Color.blurple(),
            )

        if pending_for_user:
            code, p = pending_for_user[0]
            remaining = max(0, int(p["expires_at"] - time.time()))
            embed.add_field(
                name="⏳ Pending verification",
                value=(
                    f"For **{p['mc_name']}** — run in-game within "
                    f"**{remaining // 60}m {remaining % 60}s**:\n"
                    f"```\n/trigger {OBJECTIVE} set {code}\n```"
                ),
                inline=False,
            )

        embed.set_footer(text="Only you can see this message.")
        return embed

    # --- Action helpers (used by buttons / modal) ---
    async def _start_link(self, interaction: discord.Interaction, mc_name: str):
        mc_name = mc_name.strip()
        if not MC_NAME_RE.match(mc_name):
            await interaction.response.send_message(
                "❌ That doesn't look like a valid Minecraft username.",
                ephemeral=True,
            )
            return

        discord_id = str(interaction.user.id)

        if discord_id in self.links:
            existing = self.links[discord_id]["mc_name"]
            await interaction.response.send_message(
                f"⚠️ Your Discord is already linked to **{existing}**. "
                f"Press **Unlink** first if you want to change it.",
                ephemeral=True,
            )
            return

        for info in self.links.values():
            if info["mc_name"].lower() == mc_name.lower():
                await interaction.response.send_message(
                    f"⚠️ The Minecraft account **{mc_name}** is already linked to "
                    f"another Discord user.",
                    ephemeral=True,
                )
                return

        self._purge_expired()
        for code in [
            c
            for c, p in self.pending.items()
            if p["discord_id"] == interaction.user.id
            or p["mc_name"].lower() == mc_name.lower()
        ]:
            self.pending.pop(code, None)

        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._ensure_objective()

        for _ in range(20):
            code = f"{random.randint(100000, 999999)}"
            if code not in self.pending:
                break
        else:
            await interaction.followup.send(
                "❌ Could not generate a unique code, try again.", ephemeral=True
            )
            return

        try:
            await self._rcon(f"scoreboard players enable {mc_name} {OBJECTIVE}")
        except Exception as e:
            await interaction.followup.send(
                f"❌ Could not reach the Minecraft server: `{e}`", ephemeral=True
            )
            return

        self.pending[code] = {
            "discord_id": interaction.user.id,
            "mc_name": mc_name,
            "expires_at": time.time() + CODE_TTL_SECONDS,
        }
        self._save_pending()

        await interaction.followup.send(
            embed=self._build_status_embed(interaction.user),
            view=LinkView(self, interaction.user.id),
            ephemeral=True,
        )

    async def _do_unlink(self, interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        if discord_id not in self.links:
            await interaction.response.send_message(
                "You don't have a linked account.", ephemeral=True
            )
            return
        mc_name = self.links[discord_id]["mc_name"]
        self.links.pop(discord_id, None)
        self._save_links()
        await interaction.response.send_message(
            f"✅ Unlinked from **{mc_name}**.", ephemeral=True
        )

    async def _do_whoami(self, interaction: discord.Interaction):
        info = self.links.get(str(interaction.user.id))
        if not info:
            pending_for_user = [
                p
                for p in self.pending.values()
                if p["discord_id"] == interaction.user.id
                and p["expires_at"] > time.time()
            ]
            if pending_for_user:
                msg = (
                    f"⏳ You're not linked yet — verification is **pending** for "
                    f"**{pending_for_user[0]['mc_name']}**."
                )
            else:
                msg = "You don't have a linked account. Press **Link** to start."
            await interaction.response.send_message(msg, ephemeral=True)
            return
        await interaction.response.send_message(
            f"🔗 You are linked to **{info['mc_name']}**.", ephemeral=True
        )

    # --- Slash command ---
    @app_commands.command(
        name="link",
        description="Manage the link between your Discord and Minecraft account.",
    )
    @app_commands.guilds(GUILD_ID)
    async def link(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=self._build_status_embed(interaction.user),
            view=LinkView(self, interaction.user.id),
            ephemeral=True,
        )

    # --- Background polling ---
    def _purge_expired(self):
        now = time.time()
        expired = [c for c, p in self.pending.items() if p["expires_at"] < now]
        for c in expired:
            self.pending.pop(c, None)
        if expired:
            self._save_pending()

    @tasks.loop(seconds=POLL_INTERVAL_SECONDS)
    async def poll_pending(self):
        if not self.pending:
            return

        self._purge_expired()
        if not self.pending:
            return

        # Get online players from RCON response (NOT logs).
        try:
            list_text = await self._rcon("list")
        except Exception as e:
            logger.debug(f"RCON list failed: {e}")
            return

        m = LIST_NAMES_RE.search(list_text)
        if not m:
            return
        raw = m.group(1).strip()
        if not raw:
            return
        online_lower = {
            n.strip().lower()
            for n in re.split(r"[,\s]+", raw)
            if MC_NAME_RE.match(n.strip())
        }

        # For each pending entry whose player is online, query their score.
        completed_codes = []
        for code, entry in list(self.pending.items()):
            mc_name = entry["mc_name"]
            if mc_name.lower() not in online_lower:
                continue
            try:
                resp = await self._rcon(
                    f"scoreboard players get {mc_name} {OBJECTIVE}"
                )
            except Exception as e:
                logger.debug(f"RCON get failed for {mc_name}: {e}")
                continue

            score_match = SCORE_GET_RE.search(resp)
            if not score_match:
                # No score yet (player hasn't run /trigger). Vanilla replies
                # something like "Can't get value of <obj> for <name>; none is set".
                continue
            score = score_match.group(1)
            if score != code:
                # Wrong code — could be leftover. Reset and require a new /link.
                continue

            # Match! Finalise the link.
            self.links[str(entry["discord_id"])] = {
                "mc_name": mc_name,
                "linked_at": time.time(),
            }
            completed_codes.append(code)

            # Clean up the score so the trigger is consumed.
            try:
                await self._rcon(
                    f"scoreboard players reset {mc_name} {OBJECTIVE}"
                )
            except Exception:
                pass

            # Notify the user via DM (best effort).
            user = self.bot.get_user(entry["discord_id"])
            if user is None:
                try:
                    user = await self.bot.fetch_user(entry["discord_id"])
                except Exception:
                    user = None
            if user is not None:
                try:
                    await user.send(
                        f"✅ Your Discord is now linked to Minecraft account "
                        f"**{mc_name}**."
                    )
                except discord.Forbidden:
                    pass

        if completed_codes:
            for c in completed_codes:
                self.pending.pop(c, None)
            self._save_pending()
            self._save_links()

    @poll_pending.before_loop
    async def _before_poll(self):
        await self.bot.wait_until_ready()


class LinkModal(discord.ui.Modal, title="Link Minecraft Account"):
    mc_name = discord.ui.TextInput(
        label="Minecraft username",
        placeholder="Your exact in-game name",
        min_length=3,
        max_length=16,
        required=True,
    )

    def __init__(self, cog: "AccountLink"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog._start_link(interaction, str(self.mc_name.value))


class LinkView(discord.ui.View):
    def __init__(self, cog: "AccountLink", user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id

        is_linked = str(user_id) in cog.links
        # Disable buttons that don't apply to current state.
        self.link_button.disabled = is_linked
        self.unlink_button.disabled = not is_linked

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This panel isn't yours.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Link", style=discord.ButtonStyle.success, emoji="🔗")
    async def link_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(LinkModal(self.cog))

    @discord.ui.button(label="Unlink", style=discord.ButtonStyle.danger, emoji="✂️")
    async def unlink_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.cog._do_unlink(interaction)

    @discord.ui.button(
        label="Who am I?", style=discord.ButtonStyle.secondary, emoji="❓"
    )
    async def whoami_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.cog._do_whoami(interaction)


async def setup(bot):
    await bot.add_cog(AccountLink(bot))
