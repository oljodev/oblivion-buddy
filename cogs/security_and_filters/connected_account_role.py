"""Holder CONNECTED_ACCOUNT-rollen i synk med account_link/links.json.

Brukere som har koblet Minecraft-kontoen sin får rollen, og mister den hvis
de unlinker. Discord bruker rollen til å gi tilgang til serveren — dette
erstatter det gamle filteret som blokkerte alle nye spillere.
"""

import json
import logging
from pathlib import Path

import discord
from discord.ext import commands, tasks

from config import Role

logger = logging.getLogger(__name__)

LINKS_FILE = Path(__file__).parent.parent / "account_link" / "links.json"
RECONCILE_INTERVAL_SECONDS = 60


def _load_linked_ids() -> set[int]:
    if not LINKS_FILE.exists():
        return set()
    try:
        with LINKS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load links.json: {e}")
        return set()
    out: set[int] = set()
    for k in data.keys():
        try:
            out.add(int(k))
        except ValueError:
            continue
    return out


class ConnectedAccountRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reconcile.start()

    def cog_unload(self):
        self.reconcile.cancel()

    async def _apply(self, member: discord.Member, should_have: bool):
        # Bots holdes utenfor — de styres av app_restrictions-cogen.
        if member.bot:
            return
        role = member.guild.get_role(Role.CONNECTED_ACCOUNT)
        if role is None:
            return
        has = role in member.roles
        try:
            if should_have and not has:
                await member.add_roles(role, reason="Linked Minecraft account")
            elif not should_have and has:
                await member.remove_roles(role, reason="No linked Minecraft account")
        except discord.Forbidden:
            logger.warning(
                f"Missing perms to update {role.name} for {member.name}"
            )
        except discord.HTTPException as e:
            logger.error(f"Role update failed for {member.name}: {e}")

    @tasks.loop(seconds=RECONCILE_INTERVAL_SECONDS)
    async def reconcile(self):
        linked = _load_linked_ids()
        for guild in self.bot.guilds:
            role = guild.get_role(Role.CONNECTED_ACCOUNT)
            if role is None:
                continue
            for member in guild.members:
                if member.bot:
                    continue
                await self._apply(member, member.id in linked)

    @reconcile.before_loop
    async def _before_reconcile(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        if member.id in _load_linked_ids():
            await self._apply(member, True)


async def setup(bot):
    await bot.add_cog(ConnectedAccountRole(bot))
