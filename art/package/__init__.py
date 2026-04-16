from .cog import ArtCog

async def setup(bot):
    await bot.add_cog(ArtCog(bot))
