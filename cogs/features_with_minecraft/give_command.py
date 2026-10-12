from discord.ext import commands
from aiomcrcon import Client
import config
from config import Role


class RconItemGiver(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # --- CONFIGURATION ---

        # 1. Role IDs allowed to use the command
        self.ALLOWED_ROLE_ID_1 = Role.OWNER
        self.ALLOWED_ROLE_ID_2 = Role.ADMIN

        # 2. RCON settings (loaded from environment variables)
        self.RCON_IP = config.RCON_IP
        self.RCON_PORT = config.RCON_PORT
        self.RCON_PASSWORD = config.RCON_PASS

        # 3. Default item prefix for convenience
        self.DEFAULT_PREFIX = "minecraft:"

    @commands.command(name="give")
    async def give_item(self, ctx, username: str, item_name: str, amount: int):
        """
        Gives specified items to a Minecraft player.
        Usage: !give <MinecraftName> <ItemID/ItemAlias> <amount>
        Example: !give kruk02 diamond_sword 1
        """

        # 1. AUTHORIZATION CHECK
        user_role_ids = [role.id for role in ctx.author.roles]
        required_roles = [self.ALLOWED_ROLE_ID_1, self.ALLOWED_ROLE_ID_2]

        if not any(role_id in user_role_ids for role_id in required_roles):
            # Silently ignore the command for unauthorized users
            return

        # 2. FORMAT ITEM NAME
        # Add "minecraft:" prefix if missing
        final_item_name = item_name
        if ":" not in final_item_name:
            final_item_name = f"{self.DEFAULT_PREFIX}{final_item_name}"

        # 3. EXECUTE RCON COMMAND
        try:
            client = Client(self.RCON_IP, self.RCON_PORT, self.RCON_PASSWORD)
            await client.connect()

            # Command becomes: "give <user> <item_name> <amount>"
            command = f"give {username} {final_item_name} {amount}"
            response = await client.send_cmd(command)

            await client.close()

            # 4. HANDLE RESPONSE AND ERRORS (with RCON fix)
            # Check the first part of the response to handle aiomcrcon's tuple format
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
                # MINECRAFT ERROR (e.g. unknown player, unknown item)
                await ctx.send(
                    f"⚠️ **Minecraft responded with an error:** `{response_message}`"
                )

        except Exception as e:
            # RCON CONNECTION ERROR
            await ctx.send(
                f"❌ **RCON Connection Error:** `{e}`. Please check RCON settings and server status."
            )


async def setup(bot):
    await bot.add_cog(RconItemGiver(bot))
