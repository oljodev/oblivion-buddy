import discord
from discord.ext import commands
import requests
import zipfile
import io
import json
import os

GUILD_ID = discord.Object(id=1422932147550818507)

# --- JSON History Setup ---
# os.path.dirname(__file__) gir stien til 'cogs/ticket'
HISTORY_DIR = os.path.join(os.path.dirname(__file__), "history")

# Sjekk om mappen eksisterer, ellers lag den
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)


def get_history_file_path(channel_id):
    """Returnerer filbanen for en gitt tråd/kanals ID."""
    return os.path.join(HISTORY_DIR, f"{channel_id}.json")


def load_history(channel_id):
    """Laster historikk for en gitt kanal ID."""
    path = get_history_file_path(channel_id)
    if not os.path.exists(path):
        # Dette er initialtilstanden (system/prompt)
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_history(channel_id, history_data):
    """Lagrer historikk til fil for en gitt kanal ID."""
    path = get_history_file_path(channel_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history_data, f, indent=4, ensure_ascii=False)


def delete_history(channel_id):
    """Sletter historikkfilen når tråden lukkes."""
    path = get_history_file_path(channel_id)
    if os.path.exists(path):
        os.remove(path)


# --- Slutt JSON History Setup ---


TICKET_CHANNEL_ID = 1422936354404302921

# --- Role IDs ---
OWNER_ROLE_ID = 1422933406873813254
ADMIN_ROLE_ID = 1422937935988265090
HELPER_ROLE_ID = 1422937956959785040

# --- AI stuff ---
GEMINI_API_KEY = "AIzaSyAkicIsJhMkw9MW-iJYGoJTwWWCzg1HKXQ"
MODEL = "gemini-2.0-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"

# --- Modpack scraper (Courseforge) ---
CURSEFORGE_API_KEY = "$2a$10$ZSsYO1Q6IsyUgm4Lbcs6Oe7tNUHIaDjjSHz2I4vBcG1OCfVDPKFvu"
MODPACK_ID = 1271355

headers = {"x-api-key": CURSEFORGE_API_KEY}


def fetch_modpack_mods():
    # [Din komplette fetch_modpack_mods funksjon her]
    files_url = f"https://api.curseforge.com/v1/mods/{MODPACK_ID}/files"
    files_resp = requests.get(files_url, headers=headers)
    files_data = files_resp.json()

    if "data" not in files_data or not files_data["data"]:
        print("❌ Fant ingen filer.")
        return []

    latest_file = files_data["data"][0]
    download_url = latest_file["downloadUrl"]
    if not download_url:
        print("❌ Fant ingen download URL.")
        return []

    zip_resp = requests.get(download_url)
    z = zipfile.ZipFile(io.BytesIO(zip_resp.content))

    if "manifest.json" not in z.namelist():
        print("❌ Ingen manifest.json i zippen.")
        return []

    manifest = json.loads(z.read("manifest.json"))

    mod_list = []
    for f in manifest.get("files", []):
        mod_id = f["projectID"]

        mod_url = f"https://api.curseforge.com/v1/mods/{mod_id}"
        mod_resp = requests.get(mod_url, headers=headers).json()
        if "data" in mod_resp:
            mod_name = mod_resp["data"]["name"]
            mod_list.append(mod_name)

    return mod_list


mods = fetch_modpack_mods()

# Default prompt er endret for å være et "System"-objekt i listen.
SYSTEM_PROMPT = (
    "You are a Support AI called Oblivion Buddy operating in a Minecraft server's, Discord server's Ticket channel.\n"
    "The Discord server is for the Minecraft server called Oblivion SMP.\n"
    "Always be helpful and polite. Include the username of the user asking in your responses when appropriate.\n"
    "\n"
    "Instructions:"
    "1. Be friendly, clear, and helpful. Provide concise, step-by-step guidance when needed.\n"
    "2. If you cannot answer a question, recommend that the support team takes over.\n"
    "3. Always stay within the thread you are in — do not suggest using other channels.\n"
    "4. Be concise but include all necessary information.\n"
    "5. For technical questions, guide users through solutions in a simple and easy-to-follow manner.\n"
    "\n"
    "Examples of responses:"
    " - If a user asks “How do I fix this issue?”, respond with clear, step-by-step instructions.\n"
    " - If a user asks something you cannot answer, say: “I'm not sure about this – I recommend a support team member assist you.\n"
    "\n"
    "Clarifying Questions:"
    " - If the user's message is unclear, politely ask follow-up questions to better understand the issue.\n"
    " - Do not assume the user's intent — always confirm before giving detailed instructions.\n"
    "\n"
    "Rule Violation Reports:"
    " - If a user reports another member for breaking the server rules, remain neutral and avoid taking sides.\n"
    " - Thank the user for the report and reassure them that the moderation team will review the case.\n"
    " - Do not publicly accuse or name the reported user in any channel.\n"
    " - Encourage the reporting user to provide evidence, such as screenshots or message links, if available.\n"
    " - If the issue is urgent or involves harmful behavior, immediately flag it to the human moderation team.\n"
    " - Remind users to avoid confronting the rule-breaker directly to prevent escalation.\n"
    "\n"
    "Oblivion SMP's Server Rules: \n"
    "1. Be respectful: Treat all members with kindness and respect. Personal attacks, harassment, or bullying will not be tolerated.\n"
    "2. Family-Friendly Chat: Keep language and content appropriate. Mild swearing is allowed, but offensive, explicit, or NSFW content is strictly forbidden.\n"
    "3. No cheating or Exploits: Using cheats, hacks, or exploiting server bugs to gain unfair advantages is strictly prohibited.\n"
    "4. No Griefing: Destroying, stealing, or tampering with other players' builds, items or resources is forbidden.\n"
    "5. No self-promotion: Sharing Discord server links, social media, or other promotional content without permission is not allowed.\n"
    "6. Use channels properly: Keep discussions in the correct channels to avoid confusion. Off-topic or spam messages may be removed.\n"
    "7. Respect staff decisions: Listen to moderators and admins. Arguments with staff may result in warnings or bans.\n"
    "8. No spamming: Repeated messages, excessive emojis, caps lock, or mass pinging members is not allowed.\n"
    "9. Report issues responsibly: If you encounter a problem or rule-breaking, report it to staff without public drama.\n"
    "10. Follow Discord’s Terms and Guidelines: All members must follow Discord ToS and Community Guidelines.\n"
    "\n"
    "Remember: \n"
    " - You are operating in Discord, so use Discord markdown formatting (like **bold** and *italic*) where appropriate.\n"
    " - Never ever write more than 2000 characters in a single message, so keep your responses concise.\n"
    " - If you write more than 2000 characters, you will be cut off and not be able to finish your response.\n"
    " - The user that did create the discord server, minecraft server and the Oblivion Buddy bot is called oljo1601 (or oljo).\n"
    " - oljo is the Owner of the server and should be treated with respect (Call oljo your Creator).\n"
    " - trjo (trjo3012) is the second in command (Admin) and should also be treated with respect.\n"
    " - If you can't answer a question, politely inform the user that you don't know the answer and ping the staff team. (include @Owner, witch is oljo and trjo, @Admin and @Helper)\n"
    "\n"
    "Detailed instructions about how to write in Discord: \n"
    "  -  Want to inject some flavor into your everyday text chat? Discord uses Markdown, a simple plain text formatting system that helps your sentences stand out.\n"
    "  -  Add simple characters before and after text to change formatting.\n"
    "  -  Italics use single asterisks or underscores like *italic* or _italic_.\n"
    "  -  Bold uses double asterisks like **bold**.\n"
    "  -  Bold italics combine three asterisks like ***bold italics***.\n"
    "  -  Underline uses double underscores like __underline__.\n"
    "  -  You can combine underline with bold or italics, for example __**underline bold**__.\n"
    "  -  Strikethrough uses tildes like ~~strikethrough~~.\n"
    "  -  Headers use hash marks at the start of the line, e.g., # Header, ## Subheader, ### Smaller header.\n"
    "  -  Always include a space between the hashes and the header text.\n"
    "  -  Create bulleted lists with - or * at the start of a line.\n"
    "  -  Create numbered lists using 1. 2. 3. with a space after the period.\n"
    "  -  Indent list items by adding two spaces before the bullet or number.\n"
    "  -  Inline code uses single backticks like `inline code`.\n"
    "  -  Multi-line code blocks use triple backticks on their own lines (```).\n"
    "  -  Specify a language after the opening triple backticks for syntax highlighting.\n"
    "  -  Block quotes start a line with > and include a space after the >.\n"
    "  -  Multi-line block quotes can use >>> before the first line.\n"
    "  -  Create masked (hyper)links by using [display text (For example 'Click here' or The modpack is 'Here')](https://example.com).\n"
    "  -  Spoilers wrap text in double pipes like ||spoiler|| to hide it.\n"
    "  -  Spoiler formatting is ignored inside code blocks.\n"
    "  -  Emoji can be added by typing :emoji_name: or selecting from the picker.\n"
    "  -  Use escaping (a backslash) before punctuation to prevent formatting when needed.\n"
    "  -  Remember spaces matter: always include a space after bullets, headers, and > for quotes.\n"
    "  -  Test long messages in a scratch channel to verify combined formatting looks correct.\n"
    "  -  When in doubt, wrap special characters in code formatting to preserve them.\n"
    "  -  Keep messages under 2000 characters to avoid truncation.\n"
    "\n"
    "The server uses the following mods: \n"
    + "\n".join(f" - {mod}" for mod in mods)
    + "\n"
    "\n"
    "If and when someone asks about the mod list, give them this link: [The official Oblivion SMP modpack](https://www.curseforge.com/minecraft/modpacks/the-official-oblivion-smp)\n"
    "Do not tell them how many mods there are, just tell them to open the link and check for them self.\n"
    "Do not write what mods to the user, just tell them how many and tell them to open the link and check for them self.\n"
    "Use this information to help answer questions about gameplay, features, and troubleshooting.\n"
    "\n"
    "Goal:"
    " - Help the user efficiently, politely, and professionally.\n"
    " - Keep the conversation organized within private tickets.\n"
    " - Ensure AI responses are clear, helpful, and relevant to the user’s question.\n"
    " - Always answer with the same language as the user, whether it's Norwegian, English, or another language.\n"
)


async def clean_ticket_channel(channel: discord.TextChannel):
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    # Behold første melding (eldste), slett resten
    for msg in messages[1:]:
        await msg.delete()


# --- Ticket Controls (View for Claim/Close) ---
class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # Inne i class TicketControls(discord.ui.View):

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary)
    async def ticket_claim_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):  # ENDRET NAVN HER
        await interaction.response.send_message(
            "✅ Ticket claimed. Thread will be deleted.", ephemeral=True
        )
        await interaction.channel.delete()

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def ticket_close_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):  # ENDRET NAVN HER
        thread_id = interaction.channel.id

        delete_history(thread_id)

        await interaction.response.send_message(
            "🔒 Ticket closed. Thread will be deleted.", ephemeral=True
        )
        await interaction.channel.delete()


# --- Ticket Panel View (Create Ticket) ---
class TicketPanel(discord.ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.success)
    async def create_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)

        target_channel = self.bot.get_channel(TICKET_CHANNEL_ID)

        if not isinstance(target_channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Error: Could not create thread in this channel. Check TICKET_CHANNEL_ID.",
                ephemeral=True,
            )
            return

        try:
            thread = await target_channel.create_thread(
                name=f"Ticket-{interaction.user.name}",
                type=discord.ChannelType.private_thread,
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error creating thread: {e}", ephemeral=True
            )
            return

        async for msg in thread.history(limit=5):
            if msg.type == discord.MessageType.thread_created:
                await msg.delete()
                break

        owner_role = interaction.guild.get_role(OWNER_ROLE_ID)
        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
        helper_role = interaction.guild.get_role(HELPER_ROLE_ID)

        await clean_ticket_channel(target_channel)

        pings = []
        if owner_role:
            pings.append(owner_role.mention)
        if admin_role:
            pings.append(admin_role.mention)
        if helper_role:
            pings.append(helper_role.mention)

        ping_text = " ".join(pings)

        await thread.send(f"{ping_text} {interaction.user.mention} opened a Ticket!")

        embed = discord.Embed(
            title="Ticket Created",
            description="An admin or helper will assist you shortly.\nUse `!ai <question>` to ask the AI for help.",
            color=discord.Color.dark_gray(),
        )
        await thread.send(embed=embed, view=TicketControls())

        # --- INITIALISER JSON HISTORY ---
        # Setter system/prompt som første innlegg i historikken
        initial_history = [
            {
                "role": "user",  # Bruker "user" rollen for å sette konteksten/prompten
                "parts": [
                    {
                        "text": f"{SYSTEM_PROMPT}\n\nUser creating ticket: {interaction.user.display_name}"
                    }
                ],
            }
        ]
        save_history(thread.id, initial_history)

        await interaction.followup.send(
            f"✅ Your Ticket has been created! Go to {thread.mention}", ephemeral=True
        )


# --- Tickets Cog ---
class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def on_ready_setup(self):
        """Kjøres fra main.py for å sette opp Ticket Panel og slette meldinger."""
        channel = self.bot.get_channel(TICKET_CHANNEL_ID)
        if channel:
            # Slett alle meldinger i kanalen
            await channel.purge()

            # Send new panel
            embed = discord.Embed(
                title="Need Help, Support or Assistance?",
                description="Click the button below to open a private ticket. Our admins and helpers will be notified and ready to assist you!\n\n**When to create a ticket:**  \n- Questions about the server or mods  \n- Bugs, exploits, or technical issues  \n- Help with other players or gameplay concerns  \n\n**Why use a ticket?**  \n- Private and faster support  \n- Keeps public channels clean  \n- Staff can track and solve issues efficiently  \n\n**Don’t worry!**  \nIt’s always better to open a ticket than ping staff in public channels. We’re here to help!",
                color=discord.Color.dark_blue(),
            )
            # Sender bot-objektet til View
            await channel.send(embed=embed, view=TicketPanel(self.bot))

    # --- Command to manually create panel ---
    @commands.command()
    async def createticket(self, ctx):
        # Legg til sjekk for Admin/Owner rettigheter her!
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send(
                "You do not have permission to use this command.", delete_after=5
            )

        channel = self.bot.get_channel(TICKET_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="Need Help?",
                description="Click the green button below to create a ticket.\nAdmins and helpers will be notified!",
                color=discord.Color.dark_blue(),
            )
            await channel.send(embed=embed, view=TicketPanel(self.bot))
            await ctx.send(f"✅ Ticket panel sent to {channel.mention}", delete_after=5)

    # --- AI command in threads ---
    @commands.command(
        name="ai",
        description="Ask the AI a question in your ticket thread.",
        guild=GUILD_ID,
    )
    async def ai(self, ctx, *, question: str):
        if not isinstance(
            ctx.channel, discord.Thread
        ) or not ctx.channel.name.startswith("Ticket-"):
            await ctx.send(
                "⚠️ You can only use this command inside a ticket thread.",
                delete_after=5,
            )
            return

        thread_id = ctx.channel.id

        username = ctx.author.display_name

        # 1. Last historikk fra JSON-filen
        conversation_history = load_history(thread_id)

        # Hvis historikkfilen er tom eller mangler system-prompt, initialiser
        if not conversation_history:
            # Kan skje hvis boten restarter etter at tråden er opprettet
            username = ctx.author.display_name
            conversation_history = [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"{SYSTEM_PROMPT}\n\nUser asking question: {username}"}
                    ],
                }
            ]

        # 2. Legg til det nye spørsmålet i historikken
        conversation_history.append({"role": "user", "parts": [{"text": question}]})

        headers = {"Content-Type": "application/json"}
        data = {"contents": conversation_history}

        await ctx.typing()

        try:
            resp = requests.post(URL, headers=headers, json=data)

            if resp.status_code == 200:
                json_data = resp.json()

                # Sjekker for 'candidates' før vi prøver å hente svaret
                if "candidates" in json_data and json_data["candidates"]:
                    reply = json_data["candidates"][0]["content"]["parts"][0]["text"]

                    # 3. Legg til AI-svaret i historikken
                    conversation_history.append(
                        {"role": "assistant", "parts": [{"text": reply}]}
                    )

                    # 4. Lagre oppdatert historikk til fil
                    save_history(thread_id, conversation_history)

                    await ctx.send(reply)
                else:
                    # Håndterer tilfeller der API returnerer 200, men uten et svar (f.eks. pga. safety filters)
                    await ctx.send(
                        "❌ AI failed. We are sorry, please try again later."
                    )
            else:
                await ctx.send("❌ AI Failed. We are sorry, please try again later.")
                # Logg feilen for debugging
                print(f"AI API Error Response: {resp.text}")

        except Exception as e:
            await ctx.send("❌ AI Failed. We are sorry, please try again later.")
            print(f"AI Error: {e}")


# --- NØDVENDIG: Setup Funksjon ---
async def setup(bot):
    cog = Tickets(bot)
    await bot.add_cog(cog)
    # Kjør setup-funksjonen for å sikre at panelet er på plass
    await cog.on_ready_setup()
