"""Central dev-mode switch.

Flip TEST_MODE = True to make every XP source (and pet unlocks, message-XP
level-ups, etc.) work ONLY for members with the role named in DEV_TEAM_ROLE_NAME.
Useful for testing new features in production without affecting regular users.

When TEST_MODE = False (default), every member earns XP normally.
"""

from __future__ import annotations

import discord

from config import GUILD_ID

TEST_MODE = False
DEV_TEAM_ROLE_NAME = "Dev Team"


def _has_dev_role(member: discord.Member | None) -> bool:
    if member is None:
        return False
    return any(r.name == DEV_TEAM_ROLE_NAME for r in member.roles)


def is_eligible_member(member: discord.Member | None) -> bool:
    """True if this member should receive XP/rewards right now."""
    if not TEST_MODE:
        return True
    return _has_dev_role(member)


def is_eligible_id(bot, discord_id: int) -> bool:
    """Same as is_eligible_member but takes a Discord user id and uses cached
    guild members. Returns False if the member can't be found (defensive: in
    TEST_MODE we'd rather skip than award by mistake; out of TEST_MODE we still
    return True so unlinked-but-online flows aren't blocked)."""
    if not TEST_MODE:
        return True
    guild = bot.get_guild(int(GUILD_ID))
    if guild is None:
        return False
    member = guild.get_member(discord_id)
    return _has_dev_role(member)
