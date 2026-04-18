import os
from discord.ext import commands
from aiomcrcon import Client, RCONConnectionError
import asyncio

# --- CONFIGURATION ---
from config import Role
OWNER_ROLE_ID = Role.OWNER
ADMIN_ROLE_ID = Role.ADMIN

RCON_IP = os.getenv("RCON_IP", "localhost")
RCON_PORT = int(os.getenv("RCON_PORT", 25575))
RCON_PASSWORD = os.getenv("RCON_PASS", "secret")

ALLOWED_ROLE_IDS = [OWNER_ROLE_ID, ADMIN_ROLE_ID]


class RestartControl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_authorized():
        """Check if the user has one of the allowed roles."""

        async def predicate(ctx):
            # Check if any of the user's roles match the allowed IDs
            user_role_ids = [role.id for role in ctx.author.roles]
            return any(role_id in ALLOWED_ROLE_IDS for role_id in user_role_ids)

        return commands.check(predicate)

    @commands.command(name="restart")
    @is_authorized()
    async def restart(self, ctx):
        """Saves data and stops the server to trigger an auto-restart."""
        await ctx.send("🔄 **Initiating NeoForge Restart Sequence...**")

        try:
            # Connect to RCON (Timeout set for 15s for heavy modpacks)
            async with Client(RCON_IP, RCON_PORT, RCON_PASSWORD, timeout=15) as client:
                # STEP 1: SAVE
                await ctx.send("💾 **[1/3]** Saving world data...")
                try:
                    save_response = await client.send_cmd("save-all")
                    await ctx.send(f"✅ **Save Success:** `{save_response}`")
                except Exception as e:
                    await ctx.send(
                        f"❌ **Save Failed:** `{e}`. Aborting restart for safety."
                    )
                    return

                # STEP 2: STOP
                await ctx.send("🛑 **[2/3]** Sending `stop` command...")
                # We don't 'await' the result of stop, because the server
                # often cuts the connection before it can reply.
                try:
                    await asyncio.wait_for(
                        client.send_cmd("./minecraft-restart"), timeout=5
                    )
                except (asyncio.TimeoutError, Exception):
                    # This is expected behavior as the server process terminates
                    pass

                # STEP 3: RESTART CONFIRMATION
                await ctx.send("🚀 **[3/3]** Server process terminated.")
                await ctx.send(
                    "📡 **Waiting for auto-restart loop to bring NeoForge back online...**"
                )

        except RCONConnectionError:
            await ctx.send(
                "❌ **Error:** Connection to RCON failed. Is the server already offline?"
            )
        except Exception as e:
            await ctx.send(f"⚠️ **Unexpected Error:** `{e}`")

    @restart.error
    async def restart_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(
                "⛔ **Access Denied:** You do not have the required Role ID to restart the server."
            )
        else:
            await ctx.send(f"❓ **An error occurred:** {error}")


async def setup(bot):
    await bot.add_cog(RestartControl(bot))
