from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from discord import app_commands
from discord.ext import commands
from django.db.models import Q
from django.utils import timezone

from ballsdex.core.utils.transformers import BallTransformer
from ballsdex.core.utils.utils import is_staff
from bd_models.models import Ball, Player

from ..models import ArtEntry, ArtSettings, ArtStatus

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

Interaction = discord.Interaction["BallsDexBot"]


async def get_settings() -> ArtSettings:
    """Load art settings in async context."""
    return await sync_to_async(ArtSettings.get_solo)()


async def ensure_player(user: discord.abc.User) -> Player:
    player, _ = await Player.objects.aget_or_create(discord_id=user.id)
    return player


class ArtCog(commands.GroupCog, name="art"):

    def __init__(self, bot: "BallsDexBot"):
        super().__init__()
        self.bot = bot


    async def entry_id_autocomplete(
        self, interaction: Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for entry IDs in review commands."""
        is_admin = await is_staff(interaction)

        queryset = ArtEntry.objects.all()
        if not is_admin:
            # Non-admins can only see their own entries
            player = await ensure_player(interaction.user)
            queryset = queryset.filter(artist=player)

        if current:
            try:
                # Try to parse as hex ID
                current_hex = current.strip().lstrip("#")
                current_int = int(current_hex, 16)
                queryset = queryset.filter(pk=current_int)
            except ValueError:
                # Search by title or ball name
                queryset = queryset.filter(
                    Q(title__icontains=current) | Q(ball__country__icontains=current)
                )

        entries = await sync_to_async(list)(queryset.select_related("ball")[:25])

        choices = []
        for entry in entries:
            title = entry.title or "Untitled"
            ball_name = entry.ball.country
            value = f"{entry.pk:X}"
            name = f"#{value} - {title} ({ball_name})"
            choices.append(app_commands.Choice(name=name[:100], value=value))

        return choices

    @app_commands.command(name="submit", description="Submit artwork for a ball.")
    @app_commands.describe(
        ball="The ball this artwork is for",
        attachment="Your artwork file (image, video, etc.)",
        title="Optional title for your artwork",
        description="Optional description of your artwork",
    )
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    async def art_submit(
        self,
        interaction: Interaction,
        ball: BallTransformer,
        attachment: discord.Attachment,
        title: str | None = None,
        description: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        config = await get_settings()
        if not config.enabled:
            await interaction.followup.send("Art submissions are currently disabled.", ephemeral=True)
            return

        player = await ensure_player(interaction.user)

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_submissions = await ArtEntry.objects.filter(
            artist=player, created_at__gte=today_start
        ).acount()

        if today_submissions >= config.max_submissions_per_day:
            await interaction.followup.send(
                f"You have reached the daily submission limit of {config.max_submissions_per_day} submissions. "
                "Please try again tomorrow.",
                ephemeral=True,
            )
            return

        media_url = attachment.url

        art_entry = await ArtEntry.objects.acreate(
            ball=ball,
            artist=player,
            title=title or "",
            description=description or "",
            media_url=media_url,
            status=ArtStatus.PENDING if config.require_approval else ArtStatus.APPROVED,
        )

        status_msg = (
            "Your artwork has been submitted and is pending admin approval."
            if config.require_approval
            else "Your artwork has been submitted and is now visible!"
        )

        embed = discord.Embed(
            title="✅ Artwork Submitted",
            description=status_msg,
            color=discord.Color.green(),
        )
        embed.add_field(name="Ball", value=ball.country, inline=True)
        embed.add_field(name="Entry ID", value=f"#{art_entry.pk:X}", inline=True)
        if title:
            embed.add_field(name="Title", value=title, inline=False)
        if description:
            embed.add_field(name="Description", value=description[:1024], inline=False)
        embed.set_image(url=media_url)
        embed.set_footer(text=f"Submitted at {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="view", description="View approved artwork for a ball.")
    @app_commands.describe(ball="The ball to view artwork for")
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    async def art_view(self, interaction: Interaction, ball: BallTransformer):
        """View approved art entries for a given ball with full ball details."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        config = await get_settings()
        if not config.enabled:
            await interaction.followup.send("Art viewing is currently disabled.", ephemeral=True)
            return

        entries = await sync_to_async(list)(
            ArtEntry.objects.filter(
                ball=ball,
                status=ArtStatus.APPROVED,
                enabled=True,
            )
            .select_related("artist", "ball", "ball__regime", "ball__economy")
            .order_by("-created_at")[:10]
        )

        main_embed = discord.Embed(
            title=f"🎨 Artwork for {ball.country}",
            color=discord.Color.blue(),
        )

        # Add comprehensive ball information
        main_embed.add_field(name="Ball Name", value=ball.country, inline=True)
        main_embed.add_field(name="Attack", value=str(ball.attack), inline=True)
        main_embed.add_field(name="Health", value=str(ball.health), inline=True)
        main_embed.add_field(name="Rarity", value=f"{ball.rarity:.2f}", inline=True)
        main_embed.add_field(name="Capacity Name", value=ball.capacity_name or "None", inline=True)
        main_embed.add_field(name="Tradeable", value="Yes" if ball.tradeable else "No", inline=True)

        if ball.capacity_description:
            main_embed.add_field(
                name="Capacity Description",
                value=ball.capacity_description[:1024],
                inline=False,
            )

        if ball.credits:
            main_embed.add_field(name="Art Credits", value=ball.credits, inline=True)

        if hasattr(ball, "cached_regime") and ball.cached_regime:
            main_embed.add_field(name="Regime", value=ball.cached_regime.name, inline=True)

        if hasattr(ball, "cached_economy") and ball.cached_economy:
            main_embed.add_field(name="Economy", value=ball.cached_economy.name, inline=True)

        if not entries:
            main_embed.description = "No approved artwork found for this ball."
            await interaction.followup.send(embed=main_embed, ephemeral=True)
            return

        main_embed.description = f"Found {len(entries)} approved artwork submission(s)."

        embeds = [main_embed]
        for entry in entries:
            embed = discord.Embed(
                title=entry.title or "Untitled Artwork",
                description=entry.description[:2048] if entry.description else None,
                color=discord.Color.blue(),
            )

            try:
                artist_user = await self.bot.fetch_user(entry.artist.discord_id)
                embed.set_author(name=f"By {artist_user.display_name}", icon_url=artist_user.display_avatar.url)
            except (discord.NotFound, discord.HTTPException):
                embed.set_author(name=f"By User ID: {entry.artist.discord_id}")

            embed.add_field(name="Ball", value=ball.country, inline=True)
            embed.add_field(name="Entry ID", value=f"#{entry.pk:X}", inline=True)

            if entry.media_url:
                if any(ext in entry.media_url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                    embed.set_image(url=entry.media_url)
                else:
                    embed.add_field(name="Media", value=f"[View Media]({entry.media_url})", inline=False)

            embed.timestamp = entry.created_at
            embed.set_footer(text=f"Submitted on {entry.created_at.strftime('%Y-%m-%d')}")

            embeds.append(embed)

        await interaction.followup.send(embeds=embeds[:10], ephemeral=True)  # Discord limit is 10 embeds

    @app_commands.command(name="info", description="View details of a specific art entry.")
    @app_commands.describe(entry_id="The ID of the art entry (e.g., #ABC123)")
    @app_commands.autocomplete(entry_id=entry_id_autocomplete)
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    async def art_info(self, interaction: Interaction, entry_id: str):
        """View details of a specific art entry."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Parse entry ID (remove # if present, convert hex to int)
        try:
            entry_id = entry_id.strip().lstrip("#")
            entry_pk = int(entry_id, 16)
        except ValueError:
            await interaction.followup.send(
                "Invalid entry ID format. Use format like #ABC123",
                ephemeral=True,
            )
            return

        try:
            entry = await ArtEntry.objects.select_related("ball", "artist", "reviewed_by").aget(pk=entry_pk)
        except ArtEntry.DoesNotExist:
            await interaction.followup.send("Art entry not found.", ephemeral=True)
            return

        player = await ensure_player(interaction.user)
        is_admin = await is_staff(interaction)

        if not is_admin and entry.status != ArtStatus.APPROVED and entry.artist != player:
            await interaction.followup.send("You don't have permission to view this art entry.", ephemeral=True)
            return

        embed = discord.Embed(
            title=entry.title or "Untitled Artwork",
            description=entry.description[:2048] if entry.description else "No description provided.",
            color=discord.Color.blue(),
        )

        try:
            artist_user = await self.bot.fetch_user(entry.artist.discord_id)
            embed.set_author(name=f"By {artist_user.display_name}", icon_url=artist_user.display_avatar.url)
        except (discord.NotFound, discord.HTTPException):
            embed.set_author(name=f"By User ID: {entry.artist.discord_id}")

        embed.add_field(name="Ball", value=entry.ball.country, inline=True)
        embed.add_field(name="Status", value=entry.get_status_display(), inline=True)
        embed.add_field(name="Entry ID", value=f"#{entry.pk:X}", inline=True)

        if entry.media_url:
            if any(ext in entry.media_url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                embed.set_image(url=entry.media_url)
            else:
                embed.add_field(name="Media", value=f"[View Media]({entry.media_url})", inline=False)

        if entry.reviewed_by and entry.reviewed_at:
            try:
                reviewer_user = await self.bot.fetch_user(entry.reviewed_by.discord_id)
                reviewer_name = reviewer_user.display_name
            except (discord.NotFound, discord.HTTPException):
                reviewer_name = f"User ID: {entry.reviewed_by.discord_id}"

            embed.add_field(
                name="Reviewed By",
                value=f"{reviewer_name} on {entry.reviewed_at.strftime('%Y-%m-%d %H:%M:%S')}",
                inline=False,
            )

            if entry.status == ArtStatus.REJECTED and entry.rejection_reason:
                embed.add_field(name="Rejection Reason", value=entry.rejection_reason[:1024], inline=False)

        embed.timestamp = entry.created_at
        embed.set_footer(text=f"Created on {entry.created_at.strftime('%Y-%m-%d')}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    spawn = app_commands.Group(name="spawn", description="Manage spawn art posts")
    card = app_commands.Group(name="card", description="Manage collection card art posts")

    @spawn.command(name="create", description="Create threads and post all spawn/wild art (admin only).")
    @app_commands.describe(channel="The channel to create threads in")
    @app_commands.checks.bot_has_permissions(send_messages=True, attach_files=True, manage_threads=True, create_public_threads=True)
    async def spawn_create(self, interaction: Interaction, channel: discord.TextChannel):
        """Create threads for each ball and post spawn/wild art in them."""
        if not await is_staff(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        balls = await sync_to_async(list)(
            Ball.objects.filter(enabled=True).select_related("regime", "economy").order_by("country")
        )

        if not balls:
            await interaction.followup.send("No enabled balls found.", ephemeral=True)
            return

        await interaction.followup.send(
            f"Starting to create threads and post {len(balls)} spawn art images in {channel.mention}...",
            ephemeral=True,
        )

        posted = 0
        failed = 0

        for ball in balls:
            try:
                if not ball.wild_card or not ball.wild_card.name:
                    failed += 1
                    continue

                # Get file path and create discord.File
                file_path = ball.wild_card.path
                if not os.path.exists(file_path):
                    failed += 1
                    continue

                safe_filename = "".join(c for c in ball.country if c.isalnum() or c in (" ", "-", "_")).strip()[:50]
                filename = f"{safe_filename}_spawn.png"
                file = discord.File(file_path, filename=filename)

                embed = discord.Embed(
                    title=f"{ball.country} - Spawn Art",
                    color=discord.Color.blue(),
                )
                embed.set_image(url=f"attachment://{filename}")
                embed.add_field(name="Rarity", value=f"{ball.rarity:.2f}", inline=True)
                embed.add_field(name="Attack", value=str(ball.attack), inline=True)
                embed.add_field(name="Health", value=str(ball.health), inline=True)
                embed.add_field(name="Capacity Name", value=ball.capacity_name or "None", inline=True)
                embed.add_field(name="Tradeable", value="Yes" if ball.tradeable else "No", inline=True)
                
                if ball.capacity_description:
                    embed.add_field(
                        name="Capacity Description",
                        value=ball.capacity_description[:1024],
                        inline=False,
                    )
                
                if ball.credits:
                    embed.add_field(name="Art Credits", value=ball.credits, inline=True)
                
                if hasattr(ball, "cached_regime") and ball.cached_regime:
                    embed.add_field(name="Regime", value=ball.cached_regime.name, inline=True)
                
                if hasattr(ball, "cached_economy") and ball.cached_economy:
                    embed.add_field(name="Economy", value=ball.cached_economy.name, inline=True)

                thread_name = ball.country[:100]  # Discord thread name limit
                thread = await channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=1440,  # 24 hours
                )

                await thread.send(embed=embed, file=file)
                posted += 1

                await asyncio.sleep(0.5)

            except Exception as e:
                failed += 1
                continue

        await interaction.followup.send(
            f"✅ Completed! Created {posted} threads with images, {failed} failed.",
            ephemeral=True,
        )

    @card.command(name="create", description="Create threads and post all collection card art (admin only).")
    @app_commands.describe(channel="The channel to create threads in")
    @app_commands.checks.bot_has_permissions(send_messages=True, attach_files=True, manage_threads=True, create_public_threads=True)
    async def card_create(self, interaction: Interaction, channel: discord.TextChannel):
        """Create threads for each ball and post collection card art in them."""
        if not await is_staff(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        balls = await sync_to_async(list)(
            Ball.objects.filter(enabled=True).select_related("regime", "economy").order_by("country")
        )

        if not balls:
            await interaction.followup.send("No enabled balls found.", ephemeral=True)
            return

        await interaction.followup.send(
            f"Starting to create threads and post {len(balls)} collection card images in {channel.mention}...",
            ephemeral=True,
        )

        posted = 0
        failed = 0

        for ball in balls:
            try:
                if not ball.collection_card or not ball.collection_card.name:
                    failed += 1
                    continue

                file_path = ball.collection_card.path
                if not os.path.exists(file_path):
                    failed += 1
                    continue

                safe_filename = "".join(c for c in ball.country if c.isalnum() or c in (" ", "-", "_")).strip()[:50]
                filename = f"{safe_filename}_card.png"
                file = discord.File(file_path, filename=filename)

                embed = discord.Embed(
                    title=f"{ball.country} - Collection Card",
                    color=discord.Color.blue(),
                )
                embed.set_image(url=f"attachment://{filename}")
                embed.add_field(name="Rarity", value=f"{ball.rarity:.2f}", inline=True)
                embed.add_field(name="Attack", value=str(ball.attack), inline=True)
                embed.add_field(name="Health", value=str(ball.health), inline=True)
                embed.add_field(name="Capacity Name", value=ball.capacity_name or "None", inline=True)
                embed.add_field(name="Tradeable", value="Yes" if ball.tradeable else "No", inline=True)
                
                if ball.capacity_description:
                    embed.add_field(
                        name="Capacity Description",
                        value=ball.capacity_description[:1024],
                        inline=False,
                    )
                
                if ball.credits:
                    embed.add_field(name="Art Credits", value=ball.credits, inline=True)
                
                if hasattr(ball, "cached_regime") and ball.cached_regime:
                    embed.add_field(name="Regime", value=ball.cached_regime.name, inline=True)
                
                if hasattr(ball, "cached_economy") and ball.cached_economy:
                    embed.add_field(name="Economy", value=ball.cached_economy.name, inline=True)

                thread_name = ball.country[:100]  # Discord thread name limit
                thread = await channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=1440,  # 24 hours
                )

                await thread.send(embed=embed, file=file)
                posted += 1

                await asyncio.sleep(0.5)

            except Exception as e:
                failed += 1
                continue

        await interaction.followup.send(
            f"✅ Completed! Created {posted} threads with images, {failed} failed.",
            ephemeral=True,
        )


    review = app_commands.Group(name="review", description="Review art submissions (admin only)")

    @review.command(name="list", description="List pending art submissions.")
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    async def review_list(self, interaction: Interaction):
        """List pending art submissions."""
        if not await is_staff(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        entries = await sync_to_async(list)(
            ArtEntry.objects.filter(status=ArtStatus.PENDING)
            .select_related("ball", "artist")
            .order_by("created_at")[:25]
        )

        if not entries:
            await interaction.followup.send("No pending art submissions.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 Pending Art Submissions",
            description=f"Found {len(entries)} pending submission(s).",
            color=discord.Color.orange(),
        )

        lines = []
        for entry in entries:
            try:
                artist_user = await self.bot.fetch_user(entry.artist.discord_id)
                artist_name = artist_user.display_name
            except (discord.NotFound, discord.HTTPException):
                artist_name = f"User {entry.artist.discord_id}"

            title = entry.title or "Untitled"
            entry_id = f"#{entry.pk:X}"
            lines.append(f"`{entry_id}` — **{title}** ({entry.ball.country}) by {artist_name}")

        embed.add_field(name="Pending Submissions", value="\n".join(lines[:20]), inline=False)
        if len(entries) > 20:
            embed.set_footer(text=f"Showing 20 of {len(entries)} entries. Use /art review approve/reject to manage.")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @review.command(name="approve", description="Approve an art entry (admin only).")
    @app_commands.describe(entry_id="The ID of the art entry to approve (e.g., #ABC123)")
    @app_commands.autocomplete(entry_id=entry_id_autocomplete)
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    async def review_approve(self, interaction: Interaction, entry_id: str):
        if not await is_staff(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            entry_id = entry_id.strip().lstrip("#")
            entry_pk = int(entry_id, 16)
        except ValueError:
            await interaction.followup.send("Invalid entry ID format. Use format like #ABC123", ephemeral=True)
            return

        try:
            entry = await ArtEntry.objects.select_related("ball", "artist").aget(pk=entry_pk)
        except ArtEntry.DoesNotExist:
            await interaction.followup.send("Art entry not found.", ephemeral=True)
            return

        if entry.status == ArtStatus.APPROVED:
            await interaction.followup.send("This art entry is already approved.", ephemeral=True)
            return

        reviewer = await ensure_player(interaction.user)
        entry.approve(reviewer)

        embed = discord.Embed(
            title="✅ Art Entry Approved",
            description=f"Art entry `#{entry.pk:X}` has been approved.",
            color=discord.Color.green(),
        )
        embed.add_field(name="Ball", value=entry.ball.country, inline=True)
        embed.add_field(name="Title", value=entry.title or "Untitled", inline=True)

        try:
            artist_user = await self.bot.fetch_user(entry.artist.discord_id)
            notify_embed = discord.Embed(
                title="🎨 Your Artwork Was Approved!",
                description=f"Your artwork for **{entry.ball.country}** has been approved and is now visible to everyone!",
                color=discord.Color.green(),
            )
            notify_embed.add_field(name="Entry ID", value=f"#{entry.pk:X}", inline=True)
            if entry.media_url:
                notify_embed.add_field(name="Media", value=f"[View]({entry.media_url})", inline=True)

            try:
                await artist_user.send(embed=notify_embed)
            except discord.Forbidden:
                pass  # User has DMs disabled
        except (discord.NotFound, discord.HTTPException):
            pass

        await interaction.followup.send(embed=embed, ephemeral=True)

    @review.command(name="reject", description="Reject an art entry (admin only).")
    @app_commands.describe(
        entry_id="The ID of the art entry to reject (e.g., #ABC123)",
        reason="Optional reason for rejection",
    )
    @app_commands.autocomplete(entry_id=entry_id_autocomplete)
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    async def review_reject(self, interaction: Interaction, entry_id: str, reason: str | None = None):
        """Reject an art entry with an optional reason."""
        if not await is_staff(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            entry_id = entry_id.strip().lstrip("#")
            entry_pk = int(entry_id, 16)
        except ValueError:
            await interaction.followup.send("Invalid entry ID format. Use format like #ABC123", ephemeral=True)
            return

        try:
            entry = await ArtEntry.objects.select_related("ball", "artist").aget(pk=entry_pk)
        except ArtEntry.DoesNotExist:
            await interaction.followup.send("Art entry not found.", ephemeral=True)
            return

        if entry.status == ArtStatus.REJECTED:
            await interaction.followup.send("This art entry is already rejected.", ephemeral=True)
            return

        reviewer = await ensure_player(interaction.user)
        entry.reject(reviewer, reason or "")

        embed = discord.Embed(
            title="❌ Art Entry Rejected",
            description=f"Art entry `#{entry.pk:X}` has been rejected.",
            color=discord.Color.red(),
        )
        embed.add_field(name="Ball", value=entry.ball.country, inline=True)
        embed.add_field(name="Title", value=entry.title or "Untitled", inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason[:1024], inline=False)

        try:
            artist_user = await self.bot.fetch_user(entry.artist.discord_id)
            notify_embed = discord.Embed(
                title="🎨 Your Artwork Was Rejected",
                description=f"Your artwork for **{entry.ball.country}** has been rejected.",
                color=discord.Color.red(),
            )
            notify_embed.add_field(name="Entry ID", value=f"#{entry.pk:X}", inline=True)
            if reason:
                notify_embed.add_field(name="Reason", value=reason[:1024], inline=False)

            try:
                await artist_user.send(embed=notify_embed)
            except discord.Forbidden:
                pass  # User has DMs disabled
        except (discord.NotFound, discord.HTTPException):
            pass

        await interaction.followup.send(embed=embed, ephemeral=True)

