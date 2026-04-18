import discord
from discord.ext import commands
from easy_pil import Editor, load_image_async, Font
import os
import random


class ServerGreetings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------------------------------------------------------
    # WELCOME EVENT
    # ---------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel_id = 1422933181497086122
        channel = self.bot.get_channel(channel_id)

        folder_path = "./cogs/welcome/welcome_images"

        try:
            images = [
                img
                for img in os.listdir(folder_path)
                if img.endswith((".png", ".jpg", ".jpeg"))
            ]
            random_image = random.choice(images)
            background_path = os.path.join(folder_path, random_image)
        except (FileNotFoundError, IndexError):
            print("Error: No images found in the 'cogs/welcome/welcome_images' folder.")
            return

        # Image Processing
        background = Editor(background_path).resize((800, 450))
        profile_image = await load_image_async(str(member.display_avatar.url))
        profile = Editor(profile_image).resize((150, 150)).circle_image()

        poppins = Font.poppins(size=50, variant="bold")
        poppins_small = Font.poppins(size=20, variant="light")

        background.paste(profile, (325, 90))
        background.ellipse((325, 90), 150, 150, outline="white", stroke_width=5)

        background.text(
            (400, 260),
            f"WELCOME TO {member.guild.name.upper()}",
            color="white",
            font=poppins,
            align="center",
        )

        background.text(
            (400, 325),
            f"{member.name}",
            color="white",
            font=poppins_small,
            align="center",
        )

        if channel:
            file = discord.File(fp=background.image_bytes, filename="welcome_card.jpg")
            await channel.send(f"Welcome to the server, {member.mention}!", file=file)
        else:
            print(f"Could not find channel with ID {channel_id}")

    # ---------------------------------------------------------
    # GOODBYE EVENT
    # ---------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel_id = 1422933181497086122
        channel = self.bot.get_channel(channel_id)

        # 1. Path to your folder containing goodbye background images
        # Make sure to create this folder!
        folder_path = "./cogs/welcome/welcome_images"

        # 2. Select a random image from the folder
        try:
            images = [
                img
                for img in os.listdir(folder_path)
                if img.endswith((".png", ".jpg", ".jpeg"))
            ]
            random_image = random.choice(images)
            background_path = os.path.join(folder_path, random_image)
        except (FileNotFoundError, IndexError):
            print("Error: No images found in the 'cogs/welcome/welcome_images' folder.")
            return

        # 3. Create the Editor object
        background = Editor(background_path).resize((800, 450))

        # 4. Load the user's avatar
        profile_image = await load_image_async(str(member.display_avatar.url))

        # 5. Process the profile image
        profile = Editor(profile_image).resize((150, 150)).circle_image()

        # 6. Define Fonts
        poppins = Font.poppins(size=50, variant="bold")
        poppins_small = Font.poppins(size=20, variant="light")

        # 7. Draw the elements
        background.paste(profile, (325, 90))
        background.ellipse((325, 90), 150, 150, outline="white", stroke_width=5)

        # Draw the Goodbye Text
        background.text(
            (400, 260),
            f"GOODBYE FROM {member.guild.name.upper()}",
            color="white",
            font=poppins,
            align="center",
        )

        # Draw the Username Text
        background.text(
            (400, 325),
            f"{member.name}",
            color="white",
            font=poppins_small,
            align="center",
        )

        # 8. Send the image
        if channel:
            file = discord.File(fp=background.image_bytes, filename="goodbye_card.jpg")
            await channel.send(
                f"Goodbye, {member.mention}. We hope to see you again!", file=file
            )
        else:
            print(f"Could not find channel with ID {channel_id}")


async def setup(bot):
    await bot.add_cog(ServerGreetings(bot))
