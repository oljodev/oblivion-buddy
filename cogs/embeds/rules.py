import discord
from discord.ext import commands


class Rules(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sendrules")
    @commands.has_permissions(administrator=True)
    async def send_rules(self, ctx):
        # Optional: Deletes the !sendrules command message to keep things tidy
        await ctx.message.delete()

        # Create the Embed
        embed = discord.Embed(
            title="Server Rules – Oblivion SMP",
            description="Welcome, adventurers! This server is dedicated to our modded Minecraft community.\n"
            "Please follow the rules below to ensure a fun, safe, and fair environment for everyone.\n"
            "Breaking the rules may result in warnings, mutes, kicks, or bans depending on severity.",
            color=discord.Color.red(),
        )

        # Adding the rules as Fields
        embed.add_field(
            name="1. Be Respectful",
            value="Treat all members with kindness and respect. Personal attacks, harassment, or bullying will not be tolerated.",
            inline=False,
        )
        embed.add_field(
            name="2. Family-Friendly Chat",
            value="Keep language and content appropriate. Mild swearing is allowed, but offensive, explicit, or NSFW content is strictly forbidden.",
            inline=False,
        )
        embed.add_field(
            name="3. No Cheating or Exploits",
            value="Using cheats, hacks, or exploiting server bugs to gain an unfair advantage is strictly prohibited.",
            inline=False,
        )
        embed.add_field(
            name="4. No Griefing",
            value="Destroying, stealing, or tampering with other players’ builds, items, or resources is forbidden.",
            inline=False,
        )
        embed.add_field(
            name="5. No Self-Promotion",
            value="Sharing Discord server links, social media, or other promotional content without permission is not allowed.",
            inline=False,
        )
        embed.add_field(
            name="6. Use Channels Properly",
            value="Keep discussions in the correct channels to avoid confusion. Off-topic or spam messages may be removed.",
            inline=False,
        )
        embed.add_field(
            name="7. Respect Staff Decisions",
            value="Listen to moderators and admins. Arguments with staff may result in warnings or bans.",
            inline=False,
        )
        embed.add_field(
            name="8. No Spamming",
            value="Repeated messages, excessive emojis, caps lock, or mass pinging members is prohibited.",
            inline=False,
        )
        embed.add_field(
            name="9. Report Issues Responsibly",
            value="If you encounter a problem or rule-breaking, report it to staff without public drama.",
            inline=False,
        )
        embed.add_field(
            name="10. Follow Discord ToS",
            value="All members must follow Discord ToS and Community Guidelines.",
            inline=False,
        )

        embed.add_field(
            name="Thanks!",
            value="Thanks for going through the rules! Warnings and bans aren’t fun, but they’re important to protect our community and keep things enjoyable for everyone.",
            inline=False,
        )

        # Footer and Final Message
        embed.set_footer(
            text="Let’s focus on building, exploring, and sharing adventures together!"
        )

        await ctx.send(embed=embed)


# This part is required to load the Cog
async def setup(bot):
    await bot.add_cog(Rules(bot))
