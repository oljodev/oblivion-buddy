import discord
from discord.ext import commands
from config import Channel
FORUM_CHANNEL_ID = Channel.SUGGESTIONS


class Reactions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Unicode representations of the emojis
        self.thumbs_up = "\N{THUMBS UP SIGN}"
        self.thumbs_down = "\N{THUMBS DOWN SIGN}"

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """
        Handles the creation of a new post (thread) in a Forum Channel.
        """
        # 1. Check if the new thread was created in the specified Forum Channel
        if thread.parent_id == FORUM_CHANNEL_ID:
            print(f"New post detected in configured forum channel: {thread.name}")
            try:
                # 2. Add the reactions to the initial message (the post itself)
                # We need to fetch the initial message of the thread.
                initial_message = thread.starter_message or await thread.fetch_message(
                    thread.id
                )

                # Add reactions asynchronously
                await initial_message.add_reaction(self.thumbs_up)
                await initial_message.add_reaction(self.thumbs_down)
                print(f"Successfully added reactions to post: {thread.name}")

            except discord.HTTPException as e:
                print(f"Could not add reactions to post {thread.name}: {e}")


async def setup(bot):
    await bot.add_cog(Reactions(bot))
