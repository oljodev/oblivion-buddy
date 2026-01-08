import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
import re
from datetime import datetime

# Configuration
MODPACK_ID = 1356927
UPDATE_CHANNEL_ID = 1435347662982352926
MEMBER_ROLE_ID = 1422937958897422406
VERSION_FILE = "cogs/auto_curseforge_updates/last_version.json"
CURSEFORGE_API_BASE = "https://api.curseforge.com/v1"


class AutoCurseforgeUpdates(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_version = self.load_last_version()
        self.check_updates.start()

    def load_last_version(self):
        """Load the last sent version from file."""
        if os.path.exists(VERSION_FILE):
            try:
                with open(VERSION_FILE, "r") as f:
                    data = json.load(f)
                    return data.get("version", None)
            except Exception as e:
                print(f"Error loading last version: {e}")
                return None
        return None

    def save_last_version(self, version):
        """Save the current version to file."""
        os.makedirs(os.path.dirname(VERSION_FILE), exist_ok=True)
        with open(VERSION_FILE, "w") as f:
            json.dump({"version": version}, f)
        self.last_version = version

    async def fetch_modpack_info(self, api_key=None):
        """Fetch modpack information from CurseForge API."""
        try:
            headers = {}
            if api_key:
                headers["x-api-key"] = api_key

            async with aiohttp.ClientSession() as session:
                url = f"{CURSEFORGE_API_BASE}/mods/{MODPACK_ID}"
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("data")
                    else:
                        print(f"Error fetching modpack info: {response.status}")
                        return None
        except Exception as e:
            print(f"Exception while fetching modpack info: {e}")
            return None

    async def fetch_latest_version(self, api_key=None):
        """Fetch the latest version/file info from CurseForge."""
        try:
            headers = {}
            if api_key:
                headers["x-api-key"] = api_key

            async with aiohttp.ClientSession() as session:
                url = f"{CURSEFORGE_API_BASE}/mods/{MODPACK_ID}/files"
                params = {"pageSize": 1, "sort": "dateCreated"}
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        files = data.get("data", [])
                        if files:
                            return files[0]
                        return None
                    else:
                        print(f"Error fetching latest version: {response.status}")
                        return None
        except Exception as e:
            print(f"Exception while fetching latest version: {e}")
            return None

    def convert_changelog_to_markdown(self, changelog_html):
        """Convert CurseForge changelog HTML/markup to Discord markdown."""
        if not changelog_html:
            return "No changelog available."

        text = changelog_html

        # Convert HTML tags to markdown
        # Convert <h1> to #, <h2> to ##, etc.
        text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"# \1", text, flags=re.IGNORECASE)
        text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"## \1", text, flags=re.IGNORECASE)
        text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"### \1", text, flags=re.IGNORECASE)
        text = re.sub(r"<h4[^>]*>(.*?)</h4>", r"#### \1", text, flags=re.IGNORECASE)

        # Convert <strong> and <b> to **
        text = re.sub(
            r"<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>",
            r"**\1**",
            text,
            flags=re.IGNORECASE,
        )

        # Convert <em> and <i> to *
        text = re.sub(
            r"<(?:em|i)[^>]*>(.*?)</(?:em|i)>", r"*\1*", text, flags=re.IGNORECASE
        )

        # Convert <u> to underline (Discord doesn't have native underline, use __)
        text = re.sub(r"<u[^>]*>(.*?)</u>", r"__\1__", text, flags=re.IGNORECASE)

        # Convert <li> to bullet points
        text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1", text, flags=re.IGNORECASE)

        # Remove remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Decode HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#039;", "'")

        # Clean up excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        return text if text else "No changelog available."

    async def send_update_embed(self, modpack_info, file_info, changelog):
        """Send the update embed to the configured channel."""
        try:
            channel = self.bot.get_channel(UPDATE_CHANNEL_ID)
            if not channel:
                print(f"Channel {UPDATE_CHANNEL_ID} not found!")
                return False

            # Create the embed
            embed = discord.Embed(
                title=f"📦 {modpack_info.get('name', 'Modpack')} - Update Available!",
                description=f"Version: **{file_info.get('displayName', 'Unknown')}**",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow(),
            )

            # Add changelog
            changelog_text = self.convert_changelog_to_markdown(changelog)
            # Limit to 4096 characters (Discord embed limit)
            if len(changelog_text) > 4096:
                changelog_text = changelog_text[:4093] + "..."

            embed.add_field(
                name="📝 Changelog",
                value=changelog_text if changelog_text else "No changelog available.",
                inline=False,
            )

            # Add file info
            embed.add_field(
                name="📅 Released",
                value=file_info.get("fileDate", "Unknown"),
                inline=True,
            )

            embed.add_field(
                name="📥 Downloads",
                value=str(file_info.get("downloadCount", 0)),
                inline=True,
            )

            # Add footer
            embed.set_footer(text="CurseForge Auto Update")

            # Send the embed
            await channel.send(embed=embed)

            # Send ping message
            role = channel.guild.get_role(MEMBER_ROLE_ID)
            if role:
                await channel.send(f"{role.mention} New update available!")
            else:
                print(f"Role {MEMBER_ROLE_ID} not found!")

            return True
        except Exception as e:
            print(f"Exception while sending update embed: {e}")
            return False

    @tasks.loop(minutes=15)
    async def check_updates(self):
        """Check for updates every 15 minutes."""
        try:
            if MODPACK_ID == 0 or UPDATE_CHANNEL_ID == 0 or MEMBER_ROLE_ID == 0:
                print(
                    "AutoCurseforgeUpdates: Configuration not complete. Set MODPACK_ID, UPDATE_CHANNEL_ID, and MEMBER_ROLE_ID."
                )
                return

            # Fetch latest version
            file_info = await self.fetch_latest_version()
            if not file_info:
                print("Could not fetch latest version from CurseForge")
                return

            current_version = file_info.get("id")

            # Check if this is a new version
            if current_version == self.last_version:
                print(f"No new version. Current: {current_version}")
                return

            print(
                f"New version found! Old: {self.last_version}, New: {current_version}"
            )

            # Fetch modpack info
            modpack_info = await self.fetch_modpack_info()
            if not modpack_info:
                print("Could not fetch modpack info")
                return

            # Get changelog
            changelog = file_info.get("changelog", "")

            # Send update
            success = await self.send_update_embed(modpack_info, file_info, changelog)

            if success:
                self.save_last_version(current_version)

        except Exception as e:
            print(f"Exception in check_updates: {e}")

    @check_updates.before_loop
    async def before_check_updates(self):
        """Wait for bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(AutoCurseforgeUpdates(bot))
