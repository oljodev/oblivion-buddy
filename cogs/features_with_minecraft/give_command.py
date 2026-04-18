from discord.ext import commands
import os
from aiomcrcon import Client
from config import Role


class RconItemGiver(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # --- KONFIGURASJON ---

        # 1. Rolle-IDer som har lov til å bruke kommandoen
        self.ALLOWED_ROLE_ID_1 = Role.OWNER
        self.ALLOWED_ROLE_ID_2 = Role.ADMIN

        # 2. RCON Innstillinger (Hentes fra miljøvariabler)
        self.RCON_IP = os.getenv("RCON_IP", "localhost")
        self.RCON_PORT = int(os.getenv("RCON_PORT", 25575))
        self.RCON_PASSWORD = os.getenv("RCON_PASS", "secret")

        # 3. Standard prefiks for items, for enkelhets skyld
        self.DEFAULT_PREFIX = "minecraft:"

    @commands.command(name="give")
    async def give_item(self, ctx, username: str, item_name: str, amount: int):
        """
        Gir spesifiserte items til en Minecraft-spiller.
        Bruk: !give <MinecraftNavn> <ItemID/ItemAlias> <antall>
        Eksempel: !give kruk02 diamond_sword 1
        """

        # 1. AUTORISASJONSSJEKK
        user_role_ids = [role.id for role in ctx.author.roles]
        required_roles = [self.ALLOWED_ROLE_ID_1, self.ALLOWED_ROLE_ID_2]

        if not any(role_id in user_role_ids for role_id in required_roles):
            # Ignorerer kommandoen totalt for uautoriserte brukere
            return

        # 2. FORMATER ITEM NAVNET
        # Legg til "minecraft:" prefiks hvis det mangler
        final_item_name = item_name
        if ":" not in final_item_name:
            final_item_name = f"{self.DEFAULT_PREFIX}{final_item_name}"

        # 3. UTFØR RCON-KOMMANDO
        try:
            client = Client(self.RCON_IP, self.RCON_PORT, self.RCON_PASSWORD)
            await client.connect()

            # Kommandoen blir: "give <bruker> <item_navn> <antall>"
            command = f"give {username} {final_item_name} {amount}"
            response = await client.send_cmd(command)

            await client.close()

            # 4. HÅNDTER RESPONS OG FEILMELDING (Med RCON-fiksen)
            # Sjekker den første delen av responsen for å håndtere aiomcrcon's tuple-format
            response_message = response[0] if isinstance(response, tuple) else response

            if (
                "Gave" in response_message
                or "Given" in response_message
                or "assigned" in response_message
            ):
                # SUKSESSMELDING
                await ctx.send(
                    f"✅ **Success:** Gave **{amount}x {final_item_name}** to **{username}**."
                )
            else:
                # MINECRAFT FEILMELDING (f.eks. Ukjent spiller, Ukjent item)
                await ctx.send(
                    f"⚠️ **Minecraft responded with an error:** `{response_message}`"
                )

        except Exception as e:
            # RCON TILKOBLINGSFEIL
            await ctx.send(
                f"❌ **RCON Connection Error:** `{e}`. Please check RCON settings and server status."
            )


async def setup(bot):
    await bot.add_cog(RconItemGiver(bot))
