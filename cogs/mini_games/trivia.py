import discord
import random
import asyncio
from discord import app_commands, ui
from discord.ext import commands
from config import GUILD_ID

DEFAULT_JOIN_SECONDS = 30
DEFAULT_QUESTION_SECONDS = 20
POINTS_PER_TIER = [10, 20, 35, 60, 100]  # tier 1..5

# Question format: {"q": str, "choices": [A,B,C,D], "answer": int}
# Theme: Minecraft, with some Create mod flavor.

TIER_1_EASY = [
    {
        "q": "What do you get when mining iron ore in modern Minecraft?",
        "choices": ["Iron ingot", "Raw iron", "Iron block", "Iron nugget"],
        "answer": 1,
    },
    {
        "q": "How many planks do you get from one log?",
        "choices": ["2", "3", "4", "6"],
        "answer": 2,
    },
    {
        "q": "Which mob drops string?",
        "choices": ["Zombie", "Skeleton", "Spider", "Creeper"],
        "answer": 2,
    },
    {
        "q": "What tool mines stone fastest?",
        "choices": ["Axe", "Shovel", "Pickaxe", "Hoe"],
        "answer": 2,
    },
    {
        "q": "What food is made from wheat?",
        "choices": ["Bread", "Cake only", "Pie", "Cookies only"],
        "answer": 0,
    },
    {
        "q": "How many hearts does a player have by default?",
        "choices": ["5", "10", "15", "20"],
        "answer": 1,
    },
    {
        "q": "What mob explodes when it gets close to you?",
        "choices": ["Zombie", "Skeleton", "Creeper", "Enderman"],
        "answer": 2,
    },
    {
        "q": "What do you need to sleep through the night?",
        "choices": ["A chair", "A bed", "A campfire", "A pillow"],
        "answer": 1,
    },
    {
        "q": "Which biome has cacti?",
        "choices": ["Forest", "Desert", "Plains", "Taiga"],
        "answer": 1,
    },
    {
        "q": "What do you smelt sand into?",
        "choices": ["Glass", "Sandstone", "Clay", "Salt"],
        "answer": 0,
    },
    {
        "q": "Which block does a creeper NOT damage when exploding on stone?",
        "choices": ["Dirt", "Stone", "Obsidian", "Wood"],
        "answer": 2,
    },
    {
        "q": "What do you use to tame a wolf?",
        "choices": ["Meat", "Bones", "Fish", "Wheat"],
        "answer": 1,
    },
]

TIER_2_MEDIUM = [
    {
        "q": "How many Eyes of Ender do you need to activate an End portal?",
        "choices": ["8", "10", "12", "16"],
        "answer": 2,
    },
    {
        "q": "How many wool blocks does crafting a bed require?",
        "choices": ["2", "3", "4", "6"],
        "answer": 1,
    },
    {
        "q": "Which mob drops Ender Pearls?",
        "choices": ["Ghast", "Blaze", "Enderman", "Shulker"],
        "answer": 2,
    },
    {
        "q": "What enchantment makes your tools mine faster?",
        "choices": ["Sharpness", "Efficiency", "Fortune", "Unbreaking"],
        "answer": 1,
    },
    {
        "q": "How many diamonds are needed for a full set of diamond armor?",
        "choices": ["20", "24", "28", "32"],
        "answer": 1,
    },
    {
        "q": "What does a zombie become when it drowns?",
        "choices": ["Husk", "Drowned", "Skeleton", "Zombified piglin"],
        "answer": 1,
    },
    {
        "q": "Which villager profession trades with a fletching table?",
        "choices": ["Fisherman", "Fletcher", "Leatherworker", "Arrowsmith"],
        "answer": 1,
    },
    {
        "q": "What do you combine with a Nether Star to make a beacon?",
        "choices": [
            "Diamond + Obsidian",
            "Glass + Obsidian",
            "Iron + Glass",
            "Gold + Obsidian",
        ],
        "answer": 1,
    },
    {
        "q": "What does bone meal do to a sapling?",
        "choices": [
            "Kills it",
            "Grows it instantly (sometimes)",
            "Turns it to oak",
            "Nothing",
        ],
        "answer": 1,
    },
    {
        "q": "What block is required to breed turtles?",
        "choices": ["Sand", "Sea grass", "Kelp", "Coral"],
        "answer": 1,
    },
    {
        "q": "What's the main ingredient for an awkward potion?",
        "choices": ["Spider eye", "Nether wart", "Sugar", "Glowstone"],
        "answer": 1,
    },
    {
        "q": "Which mob drops blaze rods?",
        "choices": ["Ghast", "Blaze", "Magma cube", "Wither skeleton"],
        "answer": 1,
    },
]

TIER_3_HARD = [
    {
        "q": "In Create mod, what unit is used to measure rotational force?",
        "choices": ["RPM", "Stress Units (SU)", "Torque", "Watts"],
        "answer": 1,
    },
    {
        "q": "Which redstone component outputs a signal based on container fullness?",
        "choices": ["Repeater", "Comparator", "Observer", "Target block"],
        "answer": 1,
    },
    {
        "q": "What's the bedrock floor Y-level in modern Java Edition?",
        "choices": ["-64", "-60", "-32", "0"],
        "answer": 0,
    },
    {
        "q": "Which mob only spawns when a creeper is struck by lightning?",
        "choices": [
            "Charged creeper",
            "Wither",
            "Skeleton horseman",
            "Zombie villager",
        ],
        "answer": 0,
    },
    {
        "q": "In Create mod, what does a Mechanical Press do?",
        "choices": [
            "Grinds items",
            "Compacts/presses items into plates",
            "Generates power",
            "Smelts ore",
        ],
        "answer": 1,
    },
    {
        "q": "What rare drop comes from a wither skeleton (looting 0)?",
        "choices": ["Bone", "Coal", "Wither skull", "Soul sand"],
        "answer": 2,
    },
    {
        "q": "Which ore drops the most XP when mined?",
        "choices": ["Diamond", "Emerald", "Gold", "Coal"],
        "answer": 1,
    },
    {
        "q": "In Create mod, how do you craft Andesite Alloy?",
        "choices": [
            "Andesite + Iron ingot",
            "Andesite + Iron nugget",
            "Andesite + Zinc",
            "Andesite + Copper",
        ],
        "answer": 1,
    },
    {
        "q": "What's the Mooshroom variant created by lightning striking a red mooshroom?",
        "choices": ["Pink", "Brown", "White", "Black"],
        "answer": 1,
    },
    {
        "q": "Which block pushes attached blocks when a piston moves it?",
        "choices": [
            "Slime block",
            "Honey block",
            "Both slime and honey",
            "Sticky piston only",
        ],
        "answer": 2,
    },
    {
        "q": "What does an Encased Fan blow items through when facing lava to smelt them?",
        "choices": ["Just air", "Lava (Bulk Smelting)", "Water", "Steam"],
        "answer": 1,
    },
    {
        "q": "What structure in the Deep Dark contains reinforced deepslate?",
        "choices": ["Ancient City", "Stronghold", "Monument", "Woodland mansion"],
        "answer": 0,
    },
]

TIER_4_EXPERT = [
    {
        "q": "In Create mod, what fuel lasts longest in a Blaze Burner?",
        "choices": ["Coal", "Blaze cake", "Lava bucket", "Wood"],
        "answer": 1,
    },
    {
        "q": "What's the drop rate of a totem of undying from an evoker?",
        "choices": ["25%", "50%", "75%", "100%"],
        "answer": 3,
    },
    {
        "q": "What is the maximum RPM output of a Creative Motor in Create?",
        "choices": ["64", "128", "256", "512"],
        "answer": 2,
    },
    {
        "q": "How many blocks of fall damage until a player dies (full HP, no armor)?",
        "choices": ["20", "23", "24", "30"],
        "answer": 1,
    },
    {
        "q": "In Create mod, which casing is used to encase fluid pipes?",
        "choices": ["Brass casing", "Andesite casing", "Copper casing", "Iron casing"],
        "answer": 2,
    },
    {
        "q": "What's the maximum stack size for Ender Pearls?",
        "choices": ["8", "16", "32", "64"],
        "answer": 1,
    },
    {
        "q": "Which Create mod block uses rotational power to act like a player using tools?",
        "choices": ["Mechanical Arm", "Deployer", "Drill", "Saw"],
        "answer": 1,
    },
    {
        "q": "What's the lowest Y-level where diamonds can spawn in 1.18+?",
        "choices": ["-59", "-64", "-54", "-32"],
        "answer": 1,
    },
    {
        "q": "Which mob was added to Minecraft by community vote in 2021?",
        "choices": ["Glow squid", "Copper golem", "Allay", "Iceologer"],
        "answer": 0,
    },
    {
        "q": "In Create mod, what does a Mechanical Mixer require above it?",
        "choices": ["A tank", "A Basin", "A hopper", "Nothing"],
        "answer": 1,
    },
    {
        "q": "How much stress does a Large Waterwheel provide (base)?",
        "choices": ["256 SU", "512 SU", "1024 SU", "2048 SU"],
        "answer": 2,
    },
    {
        "q": "What's the only mob that drops a Nether Star?",
        "choices": ["Ender dragon", "Wither", "Warden", "Elder guardian"],
        "answer": 1,
    },
]

TIER_5_MASTER = [
    {
        "q": "What is the blast resistance of obsidian?",
        "choices": ["600", "1200", "2400", "3,600,000"],
        "answer": 1,
    },
    {
        "q": "Who composed most of Minecraft's original soundtrack?",
        "choices": ["Lena Raine", "C418", "Kumi Tanioka", "Toby Fox"],
        "answer": 1,
    },
    {
        "q": "In Create mod, what's the base SU produced per windmill sail block (at max rotation)?",
        "choices": ["4 SU", "8 SU", "16 SU", "32 SU"],
        "answer": 2,
    },
    {
        "q": "What's the exact chance a wither skeleton drops its skull (no looting)?",
        "choices": ["1%", "2.5%", "5%", "8.5%"],
        "answer": 1,
    },
    {
        "q": "In which Minecraft version was the Warden added?",
        "choices": ["1.17", "1.18", "1.19", "1.20"],
        "answer": 2,
    },
    {
        "q": "In Create mod, what's the maximum RPM a component can handle before overstressing/speeding?",
        "choices": ["128", "256", "512", "1024"],
        "answer": 1,
    },
    {
        "q": "What's the internal name of Minecraft's 'nothing' sound event used as a placeholder?",
        "choices": [
            "null.sound",
            "minecraft:empty",
            "intentionally_blank",
            "minecraft:nothing",
        ],
        "answer": 3,
    },
    {
        "q": "How many unique paintings existed in Java Edition before the 1.21 additions?",
        "choices": ["26", "28", "32", "50"],
        "answer": 0,
    },
    {
        "q": "In Create mod, how many ingredients can a Mechanical Crafter grid craft?",
        "choices": ["Up to 4", "Up to 9", "Up to 16", "Unlimited"],
        "answer": 1,
    },
    {
        "q": "What was the first public version of Minecraft called?",
        "choices": ["Pre-Classic", "Classic", "Indev", "Infdev"],
        "answer": 0,
    },
    {
        "q": "In Create mod, what does the Rose Quartz item require to craft?",
        "choices": [
            "Redstone + quartz in a Basin",
            "Crushed quartz only",
            "Rose + quartz in crafter",
            "Netherrack + quartz",
        ],
        "answer": 0,
    },
    {
        "q": "What is the exact blast resistance of Reinforced Deepslate?",
        "choices": ["1200", "55", "1,200,000", "Unbreakable by TNT (1200+)"],
        "answer": 3,
    },
]

TIERS = [TIER_1_EASY, TIER_2_MEDIUM, TIER_3_HARD, TIER_4_EXPERT, TIER_5_MASTER]
TIER_NAMES = ["Easy", "Medium", "Hard", "Expert", "Master"]
TIER_COLORS = [
    discord.Color.green(),
    discord.Color.blue(),
    discord.Color.orange(),
    discord.Color.red(),
    discord.Color.dark_purple(),
]


class JoinView(ui.View):
    def __init__(self, game: "TriviaGame"):
        super().__init__(timeout=game.join_seconds + 5)
        self.game = game

    @ui.button(label="Join", style=discord.ButtonStyle.success, emoji="🎮")
    async def join_btn(self, interaction: discord.Interaction, button: ui.Button):
        if self.game.started:
            await interaction.response.send_message(
                "Too late — the game has already started.", ephemeral=True
            )
            return
        if interaction.user.id in self.game.players:
            await interaction.response.send_message(
                "You've already joined.", ephemeral=True
            )
            return
        self.game.players[interaction.user.id] = {
            "name": interaction.user.display_name,
            "score": 0,
        }
        await interaction.response.send_message(
            f"✅ You joined the trivia! ({len(self.game.players)} player(s) so far)",
            ephemeral=True,
        )

    @ui.button(label="Start now", style=discord.ButtonStyle.primary, emoji="▶️")
    async def start_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message(
                "Only the host can start the game early.", ephemeral=True
            )
            return
        if self.game.started:
            await interaction.response.send_message("Already starting.", ephemeral=True)
            return
        if len(self.game.players) == 0:
            await interaction.response.send_message(
                "Nobody has joined yet.", ephemeral=True
            )
            return
        await interaction.response.defer()
        self.game.early_start.set()


class QuestionView(ui.View):
    def __init__(self, game: "TriviaGame", question: dict):
        super().__init__(timeout=game.question_seconds + 5)
        self.game = game
        self.question = question
        self.answered: dict[int, int] = {}  # user_id -> choice index

        labels = ["A", "B", "C", "D"]
        for i, label in enumerate(labels):
            self.add_item(self._make_button(i, label))

    def _make_button(self, idx: int, label: str) -> ui.Button:
        btn = ui.Button(label=label, style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            if interaction.user.id not in self.game.players:
                await interaction.response.send_message(
                    "You're not in this game.", ephemeral=True
                )
                return
            if interaction.user.id in self.answered:
                await interaction.response.send_message(
                    "You already answered this question.", ephemeral=True
                )
                return
            self.answered[interaction.user.id] = idx
            await interaction.response.send_message(
                f"Locked in **{label}**.", ephemeral=True
            )
            if len(self.answered) >= len(self.game.players):
                self.game.all_answered.set()

        btn.callback = callback
        return btn


class TriviaGame:
    def __init__(
        self,
        bot: commands.Bot,
        channel: discord.TextChannel,
        host: discord.Member,
        join_seconds: int = DEFAULT_JOIN_SECONDS,
        question_seconds: int = DEFAULT_QUESTION_SECONDS,
    ):
        self.bot = bot
        self.channel = channel
        self.host_id = host.id
        self.host_name = host.display_name
        self.join_seconds = join_seconds
        self.question_seconds = question_seconds
        self.players: dict[int, dict] = {}
        self.started = False
        self.early_start = asyncio.Event()
        self.all_answered = asyncio.Event()
        self.game_msg: discord.Message | None = None

    async def run(self):
        # --- Join phase ---
        join_embed = discord.Embed(
            title="🎓 Trivia Night!",
            description=(
                f"Hosted by **{self.host_name}**.\n\n"
                f"Click **Join** to play. Starting in **{self.join_seconds}s** "
                "or when the host presses **Start now**.\n\n"
                "**Format:** 5 questions, one per difficulty tier "
                "(Easy → Master). Harder questions are worth more points."
            ),
            color=discord.Color.gold(),
        )
        join_embed.set_footer(text="oljo.dev mini-games")
        view = JoinView(self)
        join_msg = await self.channel.send(embed=join_embed, view=view)

        try:
            await asyncio.wait_for(self.early_start.wait(), timeout=self.join_seconds)
        except asyncio.TimeoutError:
            pass

        self.started = True
        for child in view.children:
            child.disabled = True

        if not self.players:
            cancelled = discord.Embed(
                title="🎓 Trivia cancelled",
                description="Nobody joined. Better luck next time!",
                color=discord.Color.red(),
            )
            try:
                await join_msg.edit(embed=cancelled, view=view)
            except discord.HTTPException:
                pass
            return

        player_list = ", ".join(p["name"] for p in self.players.values())
        join_embed.description = (
            f"Hosted by **{self.host_name}**.\n\n"
            f"**Players ({len(self.players)}):** {player_list}\n\n"
            "Game in progress below — good luck!"
        )
        try:
            await join_msg.edit(embed=join_embed, view=view)
        except discord.HTTPException:
            pass

        # --- Question phase (all edits on one shared message) ---
        for tier_idx, tier_pool in enumerate(TIERS):
            question = random.choice(tier_pool)
            await self._run_question(tier_idx, question)
            if tier_idx < len(TIERS) - 1:
                await asyncio.sleep(3)

        # --- Scoreboard (edits the same message) ---
        await self._show_scoreboard()

    async def _run_question(self, tier_idx: int, question: dict):
        tier_name = TIER_NAMES[tier_idx]
        color = TIER_COLORS[tier_idx]
        points = POINTS_PER_TIER[tier_idx]

        choice_text = "\n".join(
            f"**{chr(65 + i)}.** {c}" for i, c in enumerate(question["choices"])
        )
        embed = discord.Embed(
            title=f"Question {tier_idx + 1}/5 • {tier_name} ({points} pts)",
            description=f"{question['q']}\n\n{choice_text}",
            color=color,
        )
        embed.set_footer(text=f"You have {self.question_seconds} seconds!")

        self.all_answered = asyncio.Event()
        view = QuestionView(self, question)

        if self.game_msg is None:
            self.game_msg = await self.channel.send(embed=embed, view=view)
        else:
            await self.game_msg.edit(embed=embed, view=view)

        try:
            await asyncio.wait_for(
                self.all_answered.wait(), timeout=self.question_seconds
            )
        except asyncio.TimeoutError:
            pass

        for child in view.children:
            child.disabled = True

        correct = question["answer"]
        correct_letter = chr(65 + correct)
        correct_text = question["choices"][correct]

        winners: list[str] = []
        for uid, choice in view.answered.items():
            if choice == correct:
                self.players[uid]["score"] += points
                winners.append(self.players[uid]["name"])

        if winners:
            winner_line = f"✅ Correct: {', '.join(winners)} (+{points} pts)"
        else:
            winner_line = "❌ Nobody got it right!"

        embed.add_field(
            name=f"Answer: {correct_letter}. {correct_text}",
            value=winner_line,
            inline=False,
        )
        embed.set_footer(text="Next question coming up...")
        try:
            await self.game_msg.edit(embed=embed, view=view)
        except discord.HTTPException:
            pass

    async def _show_scoreboard(self):
        ranked = sorted(self.players.values(), key=lambda p: p["score"], reverse=True)
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, p in enumerate(ranked):
            prefix = medals[i] if i < 3 else f"**{i + 1}.**"
            lines.append(f"{prefix} {p['name']} — **{p['score']}** pts")

        winner_name = ranked[0]["name"] if ranked else "Nobody"
        embed = discord.Embed(
            title="🏆 Final Scoreboard",
            description="\n".join(lines) if lines else "No scores.",
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Winner: {winner_name}")

        if self.game_msg is None:
            await self.channel.send(embed=embed)
        else:
            await self.game_msg.edit(embed=embed, view=None)


class TriviaSetupModal(ui.Modal, title="Trivia Setup"):
    join_time = ui.TextInput(
        label="Join time (seconds)",
        default=str(DEFAULT_JOIN_SECONDS),
        min_length=1,
        max_length=4,
        required=True,
    )
    question_time = ui.TextInput(
        label="Question time (seconds)",
        default=str(DEFAULT_QUESTION_SECONDS),
        min_length=1,
        max_length=4,
        required=True,
    )

    def __init__(self, cog: "Trivia"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            js = int(self.join_time.value)
            qs = int(self.question_time.value)
        except ValueError:
            await interaction.response.send_message(
                "Please enter whole numbers for both times.", ephemeral=True
            )
            return

        if not (5 <= js <= 600) or not (5 <= qs <= 300):
            await interaction.response.send_message(
                "Join time must be 5–600s, question time 5–300s.", ephemeral=True
            )
            return

        if interaction.channel_id in self.cog.active:
            await interaction.response.send_message(
                "A trivia game is already running in this channel.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Setting up trivia...", ephemeral=True
        )
        game = TriviaGame(
            self.cog.bot, interaction.channel, interaction.user, js, qs
        )
        self.cog.active[interaction.channel_id] = game
        try:
            await game.run()
        finally:
            self.cog.active.pop(interaction.channel_id, None)


class Trivia(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active: dict[int, TriviaGame] = {}  # channel_id -> game

    @app_commands.command(
        name="trivia",
        description="Start a 5-round Minecraft trivia game with escalating difficulty.",
    )
    @app_commands.guilds(GUILD_ID)
    async def trivia(self, interaction: discord.Interaction):
        if interaction.channel_id in self.active:
            await interaction.response.send_message(
                "A trivia game is already running in this channel.", ephemeral=True
            )
            return
        await interaction.response.send_modal(TriviaSetupModal(self))


async def setup(bot: commands.Bot):
    await bot.add_cog(Trivia(bot))
