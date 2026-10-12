import discord
from discord.ext import commands
import os

from cogs._shared import dev_mode
from cogs._shared.json_store import load_json, save_json

# Aligning with your existing data structure
DATA_FOLDER = "./cogs/simple_stats/user_data"


class InviteRewards(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invites_cache = {}

        # Configuration
        self.xp_per_invite = 100
        self.dm_milestone = 5  # Send DM every 5 invites

    async def update_invite_cache(self, guild):
        """Helper function to update the invite cache for a specific guild."""
        try:
            invites = await guild.invites()
            self.invites_cache[guild.id] = {
                invite.code: invite.uses for invite in invites
            }
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        """Cache invites when the bot starts up."""
        for guild in self.bot.guilds:
            await self.update_invite_cache(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if invite.guild.id not in self.invites_cache:
            self.invites_cache[invite.guild.id] = {}
        self.invites_cache[invite.guild.id][invite.code] = invite.uses

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild.id in self.invites_cache:
            self.invites_cache[invite.guild.id].pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Fired when a new member joins to detect the inviter."""
        guild = member.guild
        if guild.id not in self.invites_cache:
            return

        old_invites = self.invites_cache[guild.id]
        try:
            new_invites = await guild.invites()
        except discord.Forbidden:
            return

        inviter = None
        for invite in new_invites:
            if invite.code in old_invites and invite.uses > old_invites[invite.code]:
                inviter = invite.inviter
                break

        await self.update_invite_cache(guild)

        if inviter and not inviter.bot:
            if not dev_mode.is_eligible_member(inviter):
                return
            await self.reward_inviter(inviter, member)

    async def reward_inviter(self, inviter, new_member):
        """Updates the existing JSON data and handles the DM logic."""
        file_path = os.path.join(DATA_FOLDER, f"{inviter.id}.json")

        # 1. Read existing data or create baseline
        user_data = {
            "user_id": inviter.id,
            "messages_sent": 0,
            "invites": 0,
            "invite_xp": 0,
        }
        user_data.update(load_json(file_path, {}))

        # 2. Increment stats
        user_data["invites"] = user_data.get("invites", 0) + 1
        user_data["invite_xp"] = user_data.get("invite_xp", 0) + self.xp_per_invite
        current_invites = user_data["invites"]

        # 3. Save data back to the JSON file
        try:
            save_json(file_path, user_data, indent=4)
        except Exception as e:
            print(f"Failed to save invite data for {inviter.name}: {e}")

        # 4. Milestone DM Check
        if current_invites % self.dm_milestone == 0:
            try:
                embed = discord.Embed(
                    title="🎉 Thank you for growing the community!",
                    description=f"You just reached **{current_invites} total invites** in **{new_member.guild.name}**!\n\n"
                    f"As a token of our gratitude, you've been awarded **{self.xp_per_invite} Bonus XP** for your latest invite.",
                    color=discord.Color.green(),
                )
                await inviter.send(embed=embed)
            except discord.Forbidden:
                pass


async def setup(bot):
    await bot.add_cog(InviteRewards(bot))
