import re
import math
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from aiomcrcon import Client

from config import Channel
from config import RCON_IP, RCON_PORT, RCON_PASS
from cogs._shared.json_store import load_json, save_json

logger = logging.getLogger("PlaytimeBoard")


OBJECTIVE = "playtime"
PAGE_SIZE = 10
REFRESH_MINUTES = 5
TICKS_PER_SECOND = 20

STATS_CHANNEL_ID = Channel.SIMPLE_STATS

STATE_FILE = Path(__file__).parent / "state.json"
SNAPSHOTS_FILE = Path(__file__).parent / "snapshots.json"
STATS_FILE = Path(__file__).parent / "stats.json"
PLAYERS_ONLINE_FILE = (
    Path(__file__).parent.parent / "simple_stats" / "players_online.json"
)
LINKS_FILE = Path(__file__).parent.parent / "account_link" / "links.json"

SNAPSHOT_RETENTION_DAYS = 31
WINDOW_30D = 30
WINDOW_7D = 7

# `<name> has 1234567 [playtime]`
SCORE_RE = re.compile(r"\bhas\s+(-?\d+)\b", re.IGNORECASE)


# Felles atomisk lagring (se cogs/_shared/json_store.py)
_atomic_write = save_json


_load_json = load_json


def format_playtime(ticks: int) -> str:
    seconds = max(0, ticks) // TICKS_PER_SECOND
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days >= 1:
        return f"{days}d {hours}h"
    if hours >= 1:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class PlaytimeBoard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = _load_json(STATE_FILE, {"message_id": 0, "current_page": 1})
        # Backwards-compat: state may predate current_page.
        self.state.setdefault("current_page", 1)
        # rows: list of (mc_name, ticks, discord_id|None) sorted desc by ticks
        self.rows: list[tuple[str, int, int | None]] = []
        self.last_update_ts: float = 0
        self._objective_ready = False
        self.refresh_loop.start()

    def _save_state(self):
        try:
            _atomic_write(STATE_FILE, self.state)
        except Exception as e:
            logger.error(f"Could not save state.json: {e}")

    def cog_unload(self):
        self.refresh_loop.cancel()

    # --- RCON helpers ---
    async def _rcon_send(self, client: Client, command: str) -> str:
        resp = await client.send_cmd(command)
        return resp[0] if isinstance(resp, tuple) else resp

    async def _ensure_objective(self, client: Client):
        if self._objective_ready:
            return
        try:
            await self._rcon_send(
                client,
                f"scoreboard objectives add {OBJECTIVE} minecraft.custom:minecraft.play_time",
            )
        except Exception as e:
            logger.warning(f"Could not ensure objective: {e}")
            return
        self._objective_ready = True

    # --- Data sources ---
    def _known_players(self) -> list[str]:
        data = _load_json(PLAYERS_ONLINE_FILE, {})
        players = data.get("players", {}) if isinstance(data, dict) else {}
        return sorted(players.keys(), key=str.lower)

    def _name_to_discord_id(self) -> dict[str, int]:
        data = _load_json(LINKS_FILE, {})
        mapping: dict[str, int] = {}
        if not isinstance(data, dict):
            return mapping
        for did, info in data.items():
            mc = info.get("mc_name") if isinstance(info, dict) else None
            if mc:
                try:
                    mapping[mc.lower()] = int(did)
                except (TypeError, ValueError):
                    pass
        return mapping

    # --- Snapshots & stats persistence ---
    def _record_snapshots(self, rows: list[tuple[str, int]]):
        """Append a snapshot per player and prune entries older than retention."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=SNAPSHOT_RETENTION_DAYS)
        data = _load_json(SNAPSHOTS_FILE, {})
        if not isinstance(data, dict):
            data = {}
        for name, ticks in rows:
            entries = data.get(name, [])
            entries.append({"ts": now.isoformat(), "ticks": int(ticks)})
            pruned = []
            for e in entries:
                ts = e.get("ts")
                if not ts:
                    continue
                try:
                    if datetime.fromisoformat(ts) >= cutoff:
                        pruned.append(e)
                except Exception:
                    continue
            data[name] = pruned
        try:
            _atomic_write(SNAPSHOTS_FILE, data)
        except Exception as e:
            logger.error(f"Could not save snapshots.json: {e}")

    def _ticks_in_window(self, name: str, current_ticks: int, days: int) -> int:
        """Ticks played in the last `days` for a player.

        Cold-start: if our oldest snapshot for this player is younger than the
        window, we can't measure properly (older playtime is invisible to us)
        so we credit the full current cumulative playtime. Once a snapshot
        is at least `days` old, strict measurement (current - oldest_in_window)
        takes over.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        entries = _load_json(SNAPSHOTS_FILE, {}).get(name, []) or []
        parsed = []
        for e in entries:
            ts = e.get("ts")
            try:
                t = datetime.fromisoformat(ts) if ts else None
            except Exception:
                t = None
            if t is None or "ticks" not in e:
                continue
            parsed.append((t, int(e["ticks"])))
        if not parsed:
            return max(0, current_ticks)
        parsed.sort()
        if parsed[0][0] > cutoff:
            return max(0, current_ticks)
        in_window = [(t, k) for t, k in parsed if t >= cutoff]
        baseline = in_window[0][1] if in_window else parsed[0][1]
        return max(0, current_ticks - baseline)

    def _write_stats(self):
        """Write a flat per-player stats file: lifetime / last 30d / last 7d."""
        now = datetime.now(timezone.utc)
        out = {"updated_at": now.isoformat(), "players": {}}
        for name, ticks, discord_id in self.rows:
            ticks_30d = self._ticks_in_window(name, ticks, WINDOW_30D)
            ticks_7d = self._ticks_in_window(name, ticks, WINDOW_7D)
            out["players"][name] = {
                "discord_id": discord_id,
                "lifetime_ticks": int(ticks),
                "lifetime": format_playtime(ticks),
                "last_30d_ticks": int(ticks_30d),
                "last_30d": format_playtime(ticks_30d),
                "last_7d_ticks": int(ticks_7d),
                "last_7d": format_playtime(ticks_7d),
            }
        try:
            _atomic_write(STATS_FILE, out)
        except Exception as e:
            logger.error(f"Could not save stats.json: {e}")

    # --- Refresh loop ---
    @tasks.loop(minutes=REFRESH_MINUTES)
    async def refresh_loop(self):
        await self._refresh()

    @refresh_loop.before_loop
    async def _before_refresh(self):
        await self.bot.wait_until_ready()

    @refresh_loop.error
    async def _refresh_error(self, error):
        logger.exception(f"Playtime refresh failed: {error}")

    async def _refresh(self):
        names = self._known_players()
        if not names:
            return

        # Single RCON connection for the whole tick.
        try:
            async with Client(RCON_IP, RCON_PORT, RCON_PASS) as client:
                await self._ensure_objective(client)

                rows: list[tuple[str, int]] = []
                for name in names:
                    try:
                        resp = await self._rcon_send(
                            client,
                            f"scoreboard players get {name} {OBJECTIVE}",
                        )
                    except Exception as e:
                        logger.debug(f"score get failed for {name}: {e}")
                        continue
                    m = SCORE_RE.search(resp or "")
                    if not m:
                        # No score yet — player hasn't logged in since the objective
                        # was created. Skip rather than show 0.
                        continue
                    rows.append((name, int(m.group(1))))
        except Exception as e:
            logger.warning(f"RCON connection failed during refresh: {e}")
            return

        rows.sort(key=lambda r: r[1], reverse=True)
        link_map = self._name_to_discord_id()
        self.rows = [
            (name, ticks, link_map.get(name.lower())) for name, ticks in rows
        ]
        self.last_update_ts = datetime.now(timezone.utc).timestamp()

        # Record raw snapshot first so window calculations have data to use,
        # then write the human-readable stats file. Order matters: snapshots
        # provide the baseline for _ticks_in_window.
        self._record_snapshots(rows)
        self._write_stats()

        await self._publish()

    # --- Embed rendering ---
    def _total_pages(self) -> int:
        if not self.rows:
            return 1
        return max(1, math.ceil(len(self.rows) / PAGE_SIZE))

    def _build_embed(self, page: int) -> discord.Embed:
        total_pages = self._total_pages()
        page = max(1, min(page, total_pages))
        start = (page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        slice_rows = self.rows[start:end]

        embed = discord.Embed(
            title="⏱️ Minecraft Playtime",
            color=discord.Color.gold(),
        )

        if not slice_rows:
            embed.description = (
                "No playtime data yet — once players log in, their total "
                "in-game time will appear here."
            )
        else:
            lines = []
            for i, (name, ticks, discord_id) in enumerate(slice_rows, start=start + 1):
                who = f"<@{discord_id}>" if discord_id else "*not linked*"
                lines.append(
                    f"**{i}.** **{name}** — {who} — `{format_playtime(ticks)}`"
                )
            embed.description = "\n".join(lines)

        if self.last_update_ts:
            updated = f"<t:{int(self.last_update_ts)}:R>"
        else:
            updated = "never"
        embed.set_footer(
            text=f"Page {page}/{total_pages} • {len(self.rows)} players"
        )
        embed.timestamp = datetime.now(timezone.utc)
        embed.add_field(name="Last updated", value=updated, inline=True)
        return embed

    # --- Persistent message management ---
    async def _publish(self):
        channel = self.bot.get_channel(STATS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(STATS_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Could not fetch SIMPLE_STATS channel: {e}")
                return

        page = self.state.get("current_page", 1)
        # Clamp current_page if the data shrank.
        page = max(1, min(page, self._total_pages()))
        if page != self.state.get("current_page"):
            self.state["current_page"] = page
            self._save_state()

        embed = self._build_embed(page)
        view = PlaytimeBoardView(self)

        message_id = self.state.get("message_id") or 0
        message = None
        fetch_failed_transiently = False
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                message = None  # really gone — fall through to send a new one
            except discord.Forbidden:
                logger.error("Missing permissions to fetch playtime message.")
                return
            except Exception as e:
                # Any other error (HTTP, rate-limit, etc.) — do not send a
                # duplicate message. Try again on the next refresh.
                logger.warning(f"fetch_message failed (transient): {e}")
                fetch_failed_transiently = True

        if fetch_failed_transiently:
            return

        try:
            if message is not None:
                await message.edit(embed=embed, view=view)
            else:
                message = await channel.send(embed=embed, view=view)
                self.state["message_id"] = message.id
                self._save_state()
        except Exception as e:
            logger.error(f"Could not publish playtime embed: {e}")



class PlaytimeBoardView(discord.ui.View):
    """Persistent view attached to the public playtime message.

    Prev/Next edit the public message in place, so all viewers see the same
    page. Current page is persisted in state.json and survives restarts.
    """

    def __init__(self, cog: PlaytimeBoard):
        super().__init__(timeout=None)
        self.cog = cog

    async def _change_page(self, interaction: discord.Interaction, direction: int):
        total = self.cog._total_pages()
        current = self.cog.state.get("current_page", 1)
        new_page = ((current - 1 + direction) % total) + 1
        self.cog.state["current_page"] = new_page
        self.cog._save_state()
        embed = self.cog._build_embed(new_page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="◀ Prev",
        style=discord.ButtonStyle.secondary,
        custom_id="playtime_board:prev",
    )
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_page(interaction, -1)

    @discord.ui.button(
        label="Next ▶",
        style=discord.ButtonStyle.secondary,
        custom_id="playtime_board:next",
    )
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._change_page(interaction, +1)


async def setup(bot: commands.Bot):
    cog = PlaytimeBoard(bot)
    await bot.add_cog(cog)
    # Register the persistent view so prev/next buttons keep working after restarts.
    bot.add_view(PlaytimeBoardView(cog))
