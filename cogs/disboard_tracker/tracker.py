import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from .disboard_core import load_data, save_data

logger = logging.getLogger(__name__)

DISBOARD_BOT_ID = 302050872383242240
ATTRIBUTION_WINDOW = timedelta(hours=2)
RETENTION_THRESHOLD = timedelta(hours=24)
MIN_BUCKET_SAMPLES = 3

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _is_bump_confirmation(message: discord.Message) -> bool:
    """DISBOARD bekrefter bump med en embed som inneholder 'Bump done'.

    Embeden kan også være lokalisert, så vi sjekker både description og
    image-url-mønsteret som DISBOARD bruker. Holder det enkelt: enhver
    embed fra DISBOARD-boten regnes som en bump-bekreftelse hvis teksten
    matcher.
    """
    if message.author.id != DISBOARD_BOT_ID:
        return False
    for embed in message.embeds:
        text = " ".join(
            filter(None, [embed.description, embed.title, embed.footer.text if embed.footer else None])
        ).lower()
        if "bump done" in text:
            return True
    return False


class DisboardTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Bump-deteksjon ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not _is_bump_confirmation(message):
            return

        now = _now()
        # DISBOARDs bekreftelse nevner brukeren som bumpet — prøv å hente ID derfra.
        bumper_id = None
        if message.mentions:
            bumper_id = message.mentions[0].id

        data = load_data()
        data["bumps"].append(
            {
                "ts": now.isoformat(),
                "weekday": now.weekday(),
                "hour": now.hour,
                "minute": now.minute,
                "bumper_id": bumper_id,
                "channel_id": message.channel.id,
            }
        )
        save_data(data)
        logger.info(
            f"DISBOARD bump registered at {now.isoformat()} (bumper={bumper_id})"
        )

    # --- Tilskriv joins til siste bump i vinduet ---
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        now = _now()
        data = load_data()
        if not data["bumps"]:
            return

        last_bump_ts = _parse(data["bumps"][-1]["ts"])
        if now - last_bump_ts > ATTRIBUTION_WINDOW:
            return  # Ikke innenfor attribusjonsvinduet — ignorer.

        data["joins"].append(
            {
                "user_id": member.id,
                "joined_ts": now.isoformat(),
                "attributed_bump_ts": last_bump_ts.isoformat(),
                "left_ts": None,
            }
        )
        save_data(data)
        logger.info(
            f"Attributed join {member.id} to bump at {last_bump_ts.isoformat()}"
        )

    # --- Retention: marker når en tilskrevet bruker forlater serveren ---
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        data = load_data()
        changed = False
        now_iso = _now().isoformat()
        for join in data["joins"]:
            if join["user_id"] == member.id and join.get("left_ts") is None:
                join["left_ts"] = now_iso
                changed = True
        if changed:
            save_data(data)
            logger.info(f"Marked attributed user {member.id} as left.")

    # --- Statistikk-kommando (kun for admin/eier) ---
    @commands.command(name="bumpstats")
    @commands.has_permissions(administrator=True)
    async def bumpstats(self, ctx: commands.Context):
        data = load_data()
        bumps = data["bumps"]
        joins = data["joins"]

        if not bumps:
            await ctx.send("No bumps recorded yet — run `/bump` and check back later.")
            return

        # Aggreger per (weekday, hour) bucket.
        bucket_bumps: dict[tuple[int, int], int] = defaultdict(int)
        for b in bumps:
            bucket_bumps[(b["weekday"], b["hour"])] += 1

        # Tilskrivne joins per bucket (basert på bumpens weekday/hour).
        bucket_joins: dict[tuple[int, int], int] = defaultdict(int)
        bucket_retained: dict[tuple[int, int], int] = defaultdict(int)
        now = _now()
        for j in joins:
            bump_ts = _parse(j["attributed_bump_ts"])
            key = (bump_ts.weekday(), bump_ts.hour)
            bucket_joins[key] += 1

            joined_ts = _parse(j["joined_ts"])
            left_ts = _parse(j["left_ts"]) if j.get("left_ts") else None
            stayed_long_enough = (
                left_ts is None and (now - joined_ts) >= RETENTION_THRESHOLD
            ) or (left_ts is not None and (left_ts - joined_ts) >= RETENTION_THRESHOLD)
            if stayed_long_enough:
                bucket_retained[key] += 1

        # Topp 5 etter avg joins per bump (kun buckets med nok prøver).
        avg_rows = []
        retention_rows = []
        for key, n_bumps in bucket_bumps.items():
            if n_bumps < MIN_BUCKET_SAMPLES:
                continue
            n_joins = bucket_joins.get(key, 0)
            avg = n_joins / n_bumps
            avg_rows.append((key, avg, n_bumps, n_joins))

            n_retained = bucket_retained.get(key, 0)
            if n_joins > 0:
                retention_rate = n_retained / n_joins
                retention_rows.append((key, retention_rate, n_bumps, n_joins, n_retained))

        avg_rows.sort(key=lambda r: r[1], reverse=True)
        retention_rows.sort(key=lambda r: r[1], reverse=True)

        embed = discord.Embed(
            title="DISBOARD Bump Stats",
            color=discord.Color.blurple(),
        )

        total_bumps = len(bumps)
        total_joins = len(joins)
        total_retained = sum(bucket_retained.values())
        retention_pct = (total_retained / total_joins * 100) if total_joins else 0.0
        embed.add_field(
            name="Totals",
            value=(
                f"Bumps: **{total_bumps}**\n"
                f"Attributed joins: **{total_joins}**\n"
                f"Retained > 24h: **{total_retained}** ({retention_pct:.0f}%)"
            ),
            inline=False,
        )

        if avg_rows:
            top = "\n".join(
                f"`{WEEKDAY_NAMES[wd]} {hr:02d}:00` — {avg:.2f} joins/bump "
                f"({nj} joins / {nb} bumps)"
                for (wd, hr), avg, nb, nj in avg_rows[:5]
            )
            embed.add_field(name="Top by joins per bump", value=top, inline=False)
        else:
            embed.add_field(
                name="Top by joins per bump",
                value=f"Not enough samples yet (need ≥ {MIN_BUCKET_SAMPLES} bumps per bucket).",
                inline=False,
            )

        if retention_rows:
            top_ret = "\n".join(
                f"`{WEEKDAY_NAMES[wd]} {hr:02d}:00` — {rate * 100:.0f}% retained "
                f"({nr}/{nj}, {nb} bumps)"
                for (wd, hr), rate, nb, nj, nr in retention_rows[:5]
            )
            embed.add_field(name="Top by retention rate", value=top_ret, inline=False)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(DisboardTracker(bot))
