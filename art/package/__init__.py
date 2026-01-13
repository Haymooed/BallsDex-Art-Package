from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    """Setup entrypoint for the art package."""
    from .cog import ArtCog

    await bot.add_cog(ArtCog(bot))
