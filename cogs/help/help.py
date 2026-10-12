"""/help and !help — one guide to everything the bot can do.

The command list is built from the commands that are actually loaded, so a
cog that is disabled (or failed to load) is left out automatically. XP numbers
are read from the XP-source cogs, so the guide stays correct if they change.
Staff commands are only shown to members who can use them.
"""

import logging
import sys

import discord
from discord import app_commands
from discord.ext import commands

import config
from config import GUILD_ID as _GUILD_ID, Channel, Role

logger = logging.getLogger("Help")

GUILD = discord.Object(id=_GUILD_ID)
COLOR = discord.Color.blurple()

# (kommando, beskrivelse). "/" = slash-kommando, "!" = prefiks-kommando.
EVERYONE_SECTIONS = [
    (
        "🔗 Minecraft",
        [
            ("/link", "Link your Discord to your Minecraft account — unlocks playtime XP, "
                      "advancement XP, daily login rewards and giveaway auto-entry."),
        ],
    ),
    (
        "📈 Levels & Stats",
        [
            ("/rank", "Your level and XP as an image card."),
            ("/leaderboard", "The server's XP leaderboard."),
            ("/pets", "Your pet collection — pick one to show on your rank card."),
            ("/streak", "Your daily login streak."),
            ("/stats", "Discord activity stats for any member."),
        ],
    ),
]

MINIGAME_SECTION = (
    "🎮 Mini-games",
    [
        ("/trivia", "5-round Minecraft trivia with escalating difficulty."),
        ("/minesweeper", "Launch the Oblivion Minesweeper Discord Activity."),
    ],
)

# (kommando, beskrivelse, hvem kan bruke den)
STAFF_COMMANDS = [
    ("/poll", "Create a timed poll.", {Role.OWNER, Role.ADMIN}),
    ("/giveaway", "Start a giveaway.", {Role.OWNER, Role.ADMIN, Role.GIVEAWAY_STAFF}),
    ("/reroll", "Pick new winners for an ended giveaway.", {Role.OWNER, Role.ADMIN, Role.GIVEAWAY_STAFF}),
    ("!give", "`!give <player> <item> <amount>` — give a Minecraft item via RCON.", {Role.OWNER, Role.ADMIN}),
    ("!bumpstats", "Disboard bump statistics.", "administrator"),
    ("!sendrules", "Post the rules embed in this channel.", "administrator"),
]


def _const(module: str, name: str, default=None):
    """Leser en konstant fra en lastet cog-modul (None hvis cogen ikke er lastet)."""
    mod = sys.modules.get(module)
    return getattr(mod, name, default) if mod else default


def _xp_lines() -> list[str]:
    lines = []
    per_msg = _const("cogs._shared.xp_store", "XP_PER_MESSAGE")
    if per_msg:
        lines.append(f"💬 **Chatting** — {per_msg} XP per message")
    voice = _const("cogs.xp_sources.voice_xp", "XP_PER_MINUTE")
    if voice:
        cap = _const("cogs.xp_sources.voice_xp", "DAILY_MINUTES_CAP")
        lines.append(f"🎙️ **Voice chat** — {voice} XP/min with at least one other person (max {cap} min/day)")
    play = _const("cogs.xp_sources.playtime_xp", "XP_PER_MINUTE")
    if play:
        cap = _const("cogs.xp_sources.playtime_xp", "DAILY_MINUTES_CAP")
        lines.append(f"⛏️ **Playing on the SMP** — {play} XP/min (max {cap} min/day) ¹")
    base = _const("cogs.xp_sources.daily_login", "BASE_BONUS")
    if base:
        per_day = _const("cogs.xp_sources.daily_login", "PER_STREAK_DAY")
        max_bonus = _const("cogs.xp_sources.daily_login", "MAX_STREAK_BONUS")
        lines.append(f"📅 **Daily login** — {base} XP + {per_day} XP per streak day (up to +{max_bonus}) ¹")
    normal = _const("cogs.xp_sources.achievement_xp", "NORMAL_XP")
    if normal:
        challenge = _const("cogs.xp_sources.achievement_xp", "CHALLENGE_XP")
        lines.append(f"🏆 **Advancements** — {normal} XP, challenges {challenge} XP ¹")
    if "cogs.xp_sources.invite_rewards" in sys.modules:
        lines.append("✉️ **Inviting friends** — bonus XP for every member you invite")
    if any("¹" in line for line in lines):
        lines.append("-# ¹ Requires a linked Minecraft account (/link)")
    return lines


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._mentions: dict[str, str] = {}
        # Erstatter discord.py sin innebygde !help med vår egen
        self._original_help = bot.help_command
        bot.help_command = None

    async def cog_unload(self):
        self.bot.help_command = self._original_help

    # ---------- helpers ----------

    async def _load_mentions(self):
        """Henter kommando-ID-er én gang, så /kommandoer blir klikkbare i hjelpen."""
        if self._mentions:
            return
        try:
            for cmd in await self.bot.tree.fetch_commands(guild=GUILD):
                self._mentions[cmd.name] = cmd.mention
        except Exception as e:
            logger.debug(f"Could not fetch command IDs for mentions: {e}")

    def _available(self, command: str) -> bool:
        name = command[1:]
        if command.startswith("!"):
            return self.bot.get_command(name) is not None
        if self.bot.tree.get_command(name, guild=GUILD) is not None:
            return True
        # Minispillene kjører på en egen bot, så vi sjekker konfigurasjonen i stedet
        if name == "trivia":
            return bool(config.MINIGAME_DISCORD_TOKEN)
        if name == "minesweeper":
            return bool(config.MINIGAME_DISCORD_TOKEN and config.MINESWEEPER_APP_ID)
        return False

    def _fmt(self, command: str) -> str:
        if command.startswith("/"):
            return self._mentions.get(command[1:], f"**{command}**")
        return f"**{command}**"

    def _section(self, entries) -> str:
        return "\n".join(
            f"{self._fmt(cmd)} — {desc}" for cmd, desc in entries if self._available(cmd)
        )

    @staticmethod
    def _can_use(member, who) -> bool:
        if not isinstance(member, discord.Member):
            return False
        if who == "administrator":
            return member.guild_permissions.administrator
        return any(r.id in who for r in member.roles)

    def build_embed(self, member) -> discord.Embed:
        embed = discord.Embed(
            title="🤖 Oblivion Buddy — Help",
            description="Here's everything I can do. Click a command or type `/` to see them all.",
            color=COLOR,
        )

        for title, entries in [*EVERYONE_SECTIONS, MINIGAME_SECTION]:
            text = self._section(entries)
            if text:
                embed.add_field(name=title, value=text, inline=False)

        xp = _xp_lines()
        if xp:
            embed.add_field(name="✨ How to earn XP", value="\n".join(xp), inline=False)

        if "cogs.ticket.ticket" in sys.modules:
            embed.add_field(
                name="🎫 Need help?",
                value=(
                    f"Open a ticket in <#{int(Channel.TICKET)}> — report a player, get support, "
                    "report a technical issue or claim a giveaway prize."
                ),
                inline=False,
            )

        staff = [
            (cmd, desc) for cmd, desc, who in STAFF_COMMANDS
            if self._can_use(member, who) and self._available(cmd)
        ]
        if staff:
            embed.add_field(name="🛠️ Staff", value=self._section(staff), inline=False)

        embed.set_footer(text="Most replies are only visible to you.")
        return embed

    # ---------- commands ----------

    @app_commands.command(name="help", description="Shows everything the bot can do.")
    @app_commands.guilds(GUILD)
    async def help_slash(self, interaction: discord.Interaction):
        await self._load_mentions()
        await interaction.response.send_message(embed=self.build_embed(interaction.user), ephemeral=True)

    @commands.command(name="help")
    async def help_prefix(self, ctx: commands.Context):
        await self._load_mentions()
        # I DM-er har vi ikke roller, så slå opp medlemmet i serveren for staff-delen
        member = ctx.author
        if not isinstance(member, discord.Member):
            guild = self.bot.get_guild(_GUILD_ID)
            member = guild.get_member(ctx.author.id) if guild else None
        await ctx.reply(embed=self.build_embed(member), mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
