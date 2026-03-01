from __future__ import annotations

import asyncio
import logging
import os
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

log = logging.getLogger(__name__)
Interaction = discord.Interaction["BallsDexBot"]

_PAGE_SIZE = 5 


async def _ensure_player(user: discord.abc.User) -> Player:
    player, _ = await Player.objects.aget_or_create(discord_id=user.id)
    return player


def _entry_id_to_int(raw: str) -> int | None:
    try:
        return int(raw.strip().lstrip("#"), 16)
    except (ValueError, AttributeError):
        return None


def _build_entry_embed(entry: ArtEntry, artist_user: discord.User | None) -> discord.Embed:
    """Build a rich embed for a single ArtEntry."""
    embed = discord.Embed(
        title=entry.display_title,
        description=entry.description[:2048] if entry.description else None,
        colour=discord.Colour.blue(),
    )
    if artist_user:
        embed.set_author(
            name=f"By {artist_user.display_name}",
            icon_url=artist_user.display_avatar.url,
        )
    else:
        embed.set_author(name=f"By User ID: {entry.artist.discord_id}")

    embed.add_field(name="Ball", value=entry.ball.country, inline=True)
    embed.add_field(name="Entry ID", value=f"#{entry.pk:X}", inline=True)
    embed.add_field(name="Status", value=entry.get_status_display(), inline=True)

    if entry.media_url:
        if entry.is_image_url():
            embed.set_image(url=entry.media_url)
        else:
            embed.add_field(name="Media", value=f"[View ↗]({entry.media_url})", inline=False)

    if entry.reviewed_by and entry.reviewed_at:
        embed.add_field(
            name="Reviewed at",
            value=discord.utils.format_dt(entry.reviewed_at, style="f"),
            inline=True,
        )
    if entry.status == ArtStatus.REJECTED and entry.rejection_reason:
        embed.add_field(name="Rejection reason", value=entry.rejection_reason[:512], inline=False)

    embed.set_footer(text=f"Submitted • #{entry.pk:X}")
    embed.timestamp = entry.created_at
    return embed



class ArtPaginator(discord.ui.View):
    """Simple button paginator for /art view."""

    def __init__(
        self,
        pages: list[discord.Embed],
        *,
        author_id: int,
        timeout: float = 120.0,
    ):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author_id = author_id
        self.current = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current >= len(self.pages) - 1
        self.counter.label = f"{self.current + 1} / {len(self.pages)}"

    async def _edit(self, interaction: Interaction) -> None:
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your paginator.", ephemeral=True)
            return
        self.current -= 1
        await self._edit(interaction)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.primary, disabled=True)
    async def counter(self, interaction: Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your paginator.", ephemeral=True)
            return
        self.current += 1
        await self._edit(interaction)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]



class ArtCog(commands.GroupCog, name="art"):
    """Community art submission and display system."""

    def __init__(self, bot: "BallsDexBot"):
        super().__init__()
        self.bot = bot


    async def _fetch_user_safe(self, discord_id: int) -> discord.User | None:
        try:
            return await self.bot.fetch_user(discord_id)
        except (discord.NotFound, discord.HTTPException):
            return None

    async def _notify_artist(self, entry: ArtEntry, embed: discord.Embed) -> None:
        artist_user = await self._fetch_user_safe(entry.artist.discord_id)
        if artist_user:
            try:
                await artist_user.send(embed=embed)
            except discord.Forbidden:
                pass  # DMs disabled


    async def _entry_id_autocomplete(
        self,
        interaction: Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        admin = await is_staff(interaction)
        qs = ArtEntry.objects.select_related("ball")

        if not admin:
            player = await _ensure_player(interaction.user)
            qs = qs.filter(artist=player)

        if current:
            pk = _entry_id_to_int(current)
            if pk is not None:
                qs = qs.filter(pk=pk)
            else:
                qs = qs.filter(
                    Q(title__icontains=current) | Q(ball__country__icontains=current)
                )

        entries = await sync_to_async(list)(qs[:25])
        return [
            app_commands.Choice(
                name=f"#{e.pk:X} – {e.display_title} ({e.ball.country}) [{e.get_status_display()}]"[:100],
                value=f"{e.pk:X}",
            )
            for e in entries
        ]


    @app_commands.command(name="submit", description="Submit artwork for a ball.")
    @app_commands.describe(
        ball="The ball this artwork is for.",
        attachment="Your artwork file (image, etc.).",
        title="Optional title for your artwork.",
        description="Optional description of your artwork.",
    )
    async def art_submit(
        self,
        interaction: Interaction,
        ball: BallTransformer,
        attachment: discord.Attachment,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        config = await ArtSettings.load()
        if not config.enabled:
            await interaction.followup.send("Art submissions are currently disabled.", ephemeral=True)
            return

        if attachment.content_type and not attachment.content_type.startswith(("image/", "video/")):
            await interaction.followup.send(
                "Only image or video files are accepted.", ephemeral=True
            )
            return

        player = await _ensure_player(interaction.user)

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = await ArtEntry.objects.filter(
            artist=player, created_at__gte=today_start
        ).acount()
        if today_count >= config.max_submissions_per_day:
            await interaction.followup.send(
                f"You've reached today's limit of **{config.max_submissions_per_day}** submission(s). "
                "Try again tomorrow!",
                ephemeral=True,
            )
            return

        initial_status = ArtStatus.PENDING if config.require_approval else ArtStatus.APPROVED
        entry = await ArtEntry.objects.acreate(
            ball=ball,
            artist=player,
            title=title or "",
            description=description or "",
            media_url=attachment.url,
            status=initial_status,
        )

        status_line = (
            "⏳ Your submission is **pending admin review** before it becomes visible."
            if config.require_approval
            else "✅ Auto-approved — your artwork is now visible!"
        )

        embed = discord.Embed(
            title="🎨 Artwork Submitted",
            description=status_line,
            colour=discord.Colour.green(),
        )
        embed.add_field(name="Ball", value=ball.country, inline=True)
        embed.add_field(name="Entry ID", value=f"#{entry.pk:X}", inline=True)
        if title:
            embed.add_field(name="Title", value=title, inline=False)
        if description:
            embed.add_field(name="Description", value=description[:512], inline=False)
        if entry.is_image_url():
            embed.set_image(url=attachment.url)
        embed.set_footer(text=f"Use /art info {entry.pk:X} to check your submission")

        await interaction.followup.send(embed=embed, ephemeral=True)


    @app_commands.command(name="view", description="Browse approved artwork for a ball.")
    @app_commands.describe(ball="The ball to view artwork for.")
    async def art_view(self, interaction: Interaction, ball: BallTransformer) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        config = await ArtSettings.load()
        if not config.enabled:
            await interaction.followup.send("Art viewing is currently disabled.", ephemeral=True)
            return

        entries = await sync_to_async(list)(
            ArtEntry.objects.filter(ball=ball, status=ArtStatus.APPROVED, enabled=True)
            .select_related("artist", "ball")
            .order_by("-created_at")
        )

        if not entries:
            embed = discord.Embed(
                title=f"🎨 Artwork for {ball.country}",
                description="No approved artwork found for this ball yet.\nBe the first — use `/art submit`!",
                colour=discord.Colour.greyple(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        pages: list[discord.Embed] = []
        for entry in entries:
            artist_user = await self._fetch_user_safe(entry.artist.discord_id)
            embed = _build_entry_embed(entry, artist_user)
            embed.title = f"🎨 {ball.country} — {embed.title}"
            pages.append(embed)

        for i, page in enumerate(pages):
            page.set_footer(text=f"Page {i+1}/{len(pages)} • #{entries[i].pk:X}")

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0], ephemeral=True)
        else:
            view = ArtPaginator(pages, author_id=interaction.user.id)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)


    @app_commands.command(name="info", description="View details of a specific art entry.")
    @app_commands.describe(entry_id="The entry ID (e.g. 1A2B).")
    @app_commands.autocomplete(entry_id=_entry_id_autocomplete)
    async def art_info(self, interaction: Interaction, entry_id: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        pk = _entry_id_to_int(entry_id)
        if pk is None:
            await interaction.followup.send("Invalid entry ID — use the format shown in autocomplete.", ephemeral=True)
            return

        try:
            entry = await ArtEntry.objects.select_related("ball", "artist", "reviewed_by").aget(pk=pk)
        except ArtEntry.DoesNotExist:
            await interaction.followup.send("Entry not found.", ephemeral=True)
            return

        player = await _ensure_player(interaction.user)
        admin = await is_staff(interaction)

        if not admin and entry.status != ArtStatus.APPROVED and entry.artist_id != player.pk:
            await interaction.followup.send("You don't have permission to view this entry.", ephemeral=True)
            return

        artist_user = await self._fetch_user_safe(entry.artist.discord_id)
        embed = _build_entry_embed(entry, artist_user)

        if (admin or entry.artist_id == player.pk) and entry.reviewed_by and entry.reviewed_at:
            reviewer_user = await self._fetch_user_safe(entry.reviewed_by.discord_id)
            reviewer_name = reviewer_user.display_name if reviewer_user else f"ID {entry.reviewed_by.discord_id}"
            embed.add_field(
                name="Reviewer",
                value=f"{reviewer_name} • {discord.utils.format_dt(entry.reviewed_at, style='f')}",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


    @app_commands.command(name="mine", description="View your own art submissions.")
    @app_commands.describe(status="Filter by status (leave blank for all).")
    @app_commands.choices(status=[
        app_commands.Choice(name="Pending", value="pending"),
        app_commands.Choice(name="Approved", value="approved"),
        app_commands.Choice(name="Rejected", value="rejected"),
    ])
    async def art_mine(self, interaction: Interaction, status: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        player = await _ensure_player(interaction.user)
        qs = ArtEntry.objects.filter(artist=player).select_related("ball").order_by("-created_at")

        if status:
            qs = qs.filter(status=status)

        entries = await sync_to_async(list)(qs[:50])

        if not entries:
            label = f"**{status}**" if status else "any"
            await interaction.followup.send(
                f"You have no {label} submissions.", ephemeral=True
            )
            return

        pages: list[discord.Embed] = []
        for chunk_start in range(0, len(entries), _PAGE_SIZE):
            chunk = entries[chunk_start : chunk_start + _PAGE_SIZE]
            embed = discord.Embed(
                title="🖼️ Your Submissions",
                colour=discord.Colour.blurple(),
            )
            for entry in chunk:
                status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(entry.status, "❓")
                value_parts = [
                    f"{status_icon} **{entry.get_status_display()}**",
                    f"Ball: {entry.ball.country}",
                ]
                if entry.rejection_reason:
                    value_parts.append(f"Reason: {entry.rejection_reason[:100]}")
                embed.add_field(
                    name=f"#{entry.pk:X} — {entry.display_title}",
                    value="\n".join(value_parts),
                    inline=False,
                )
            pages.append(embed)

        for i, page in enumerate(pages):
            page.set_footer(text=f"Page {i+1}/{len(pages)} • {len(entries)} submission(s) total")

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0], ephemeral=True)
        else:
            view = ArtPaginator(pages, author_id=interaction.user.id)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)


    review = app_commands.Group(name="review", description="Manage art submissions (admin only).")

    @review.command(name="list", description="List art submissions.")
    @app_commands.describe(status="Filter by status (default: pending).")
    @app_commands.choices(status=[
        app_commands.Choice(name="Pending", value="pending"),
        app_commands.Choice(name="Approved", value="approved"),
        app_commands.Choice(name="Rejected", value="rejected"),
    ])
    async def review_list(self, interaction: Interaction, status: str = "pending") -> None:
        if not await is_staff(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        entries = await sync_to_async(list)(
            ArtEntry.objects.filter(status=status)
            .select_related("ball", "artist")
            .order_by("created_at")[:25]
        )

        status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(status, "❓")
        embed = discord.Embed(
            title=f"{status_icon} Art Submissions — {status.capitalize()}",
            colour=discord.Colour.orange(),
        )

        if not entries:
            embed.description = f"No {status} submissions found."
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        lines = []
        for entry in entries:
            artist_user = await self._fetch_user_safe(entry.artist.discord_id)
            artist_name = artist_user.display_name if artist_user else f"ID {entry.artist.discord_id}"
            ts = discord.utils.format_dt(entry.created_at, style="d")
            lines.append(
                f"`#{entry.pk:X}` **{entry.display_title}** ({entry.ball.country})"
                f"\n└ by {artist_name} • {ts}"
            )

        embed.description = "\n\n".join(lines)
        embed.set_footer(text=f"Showing up to 25 entries. Use /art review approve/reject to act.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @review.command(name="approve", description="Approve an art entry.")
    @app_commands.describe(entry_id="The entry ID to approve.")
    @app_commands.autocomplete(entry_id=_entry_id_autocomplete)
    async def review_approve(self, interaction: Interaction, entry_id: str) -> None:
        if not await is_staff(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        pk = _entry_id_to_int(entry_id)
        if pk is None:
            await interaction.followup.send("Invalid entry ID.", ephemeral=True)
            return

        try:
            entry = await ArtEntry.objects.select_related("ball", "artist").aget(pk=pk)
        except ArtEntry.DoesNotExist:
            await interaction.followup.send("Entry not found.", ephemeral=True)
            return

        if entry.status == ArtStatus.APPROVED:
            await interaction.followup.send("This entry is already approved.", ephemeral=True)
            return

        reviewer = await _ensure_player(interaction.user)
        await sync_to_async(entry.approve)(reviewer)

        embed = discord.Embed(
            title="✅ Entry Approved",
            description=f"Entry `#{entry.pk:X}` — **{entry.display_title}** ({entry.ball.country}) has been approved.",
            colour=discord.Colour.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        notify = discord.Embed(
            title="🎨 Your Artwork Was Approved!",
            description=(
                f"Your artwork for **{entry.ball.country}** has been approved "
                "and is now visible to everyone with `/art view`."
            ),
            colour=discord.Colour.green(),
        )
        notify.add_field(name="Entry ID", value=f"#{entry.pk:X}", inline=True)
        notify.add_field(name="Title", value=entry.display_title, inline=True)
        if entry.media_url and entry.is_image_url():
            notify.set_thumbnail(url=entry.media_url)
        await self._notify_artist(entry, notify)

    @review.command(name="reject", description="Reject an art entry.")
    @app_commands.describe(
        entry_id="The entry ID to reject.",
        reason="Optional reason for rejection.",
    )
    @app_commands.autocomplete(entry_id=_entry_id_autocomplete)
    async def review_reject(
        self, interaction: Interaction, entry_id: str, reason: str | None = None
    ) -> None:
        if not await is_staff(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        pk = _entry_id_to_int(entry_id)
        if pk is None:
            await interaction.followup.send("Invalid entry ID.", ephemeral=True)
            return

        try:
            entry = await ArtEntry.objects.select_related("ball", "artist").aget(pk=pk)
        except ArtEntry.DoesNotExist:
            await interaction.followup.send("Entry not found.", ephemeral=True)
            return

        if entry.status == ArtStatus.REJECTED:
            await interaction.followup.send("This entry is already rejected.", ephemeral=True)
            return

        reviewer = await _ensure_player(interaction.user)
        await sync_to_async(entry.reject)(reviewer, reason or "")

        embed = discord.Embed(
            title="❌ Entry Rejected",
            description=f"Entry `#{entry.pk:X}` — **{entry.display_title}** ({entry.ball.country}) has been rejected.",
            colour=discord.Colour.red(),
        )
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Notify artist
        notify = discord.Embed(
            title="🎨 Your Artwork Was Rejected",
            description=f"Your artwork for **{entry.ball.country}** was not approved.",
            colour=discord.Colour.red(),
        )
        notify.add_field(name="Entry ID", value=f"#{entry.pk:X}", inline=True)
        notify.add_field(name="Title", value=entry.display_title, inline=True)
        if reason:
            notify.add_field(name="Reason", value=reason[:1024], inline=False)
        await self._notify_artist(entry, notify)


    spawn = app_commands.Group(name="spawn", description="Spawn art forum utilities (admin only).")
    card = app_commands.Group(name="card", description="Collection card forum utilities (admin only).")

    async def _create_forum_posts(
        self,
        interaction: Interaction,
        channel: discord.ForumChannel,
        *,
        image_attr: str,
        filename_suffix: str,
        embed_title_suffix: str,
    ) -> None:
        """Shared implementation for spawn and card forum post creation."""
        if not await is_staff(interaction):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        config = await ArtSettings.load()

        balls = await sync_to_async(list)(
            Ball.objects.filter(enabled=True)
            .select_related("regime", "economy")
            .order_by("country")
        )

        if not balls:
            await interaction.followup.send("No enabled balls found.", ephemeral=True)
            return

        ball_names = {b.country for b in balls}
        safe = set(config.safe_thread_names)

        existing_threads: set[discord.Thread] = set(channel.threads)
        async for t in channel.archived_threads(limit=None):
            existing_threads.add(t)
        existing_thread_names = {t.name for t in existing_threads}

        for thread in existing_threads:
            if thread.name not in ball_names and thread.name not in safe:
                try:
                    await thread.delete()
                except Exception:
                    log.warning("Could not delete stale thread %r", thread.name)

        balls_to_create = [b for b in balls if b.country not in existing_thread_names]

        skipped_count = len(balls) - len(balls_to_create)
        note = f" ({skipped_count} already exist)" if skipped_count else ""
        await interaction.followup.send(
            f"⏳ Creating **{len(balls_to_create)}** forum posts in {channel.mention}…{note}",
            ephemeral=True,
        )

        posted = 0
        failed = 0

        for ball in balls_to_create:
            try:
                img_field = getattr(ball, image_attr, None)
                if not img_field or not img_field.name:
                    failed += 1
                    continue

                file_path: str = img_field.path
                if not os.path.exists(file_path):
                    failed += 1
                    continue

                safe_name = "".join(
                    c for c in ball.country if c.isalnum() or c in (" ", "-", "_")
                ).strip()[:50]
                fname = f"{safe_name}_{filename_suffix}.png"
                dfile = discord.File(file_path, filename=fname)

                embed = discord.Embed(
                    title=f"{ball.country} — {embed_title_suffix}",
                    colour=discord.Colour.blue(),
                )
                embed.set_image(url=f"attachment://{fname}")
                embed.add_field(name="Rarity", value=f"{ball.rarity:.2f}", inline=True)
                embed.add_field(name="Attack", value=str(ball.attack), inline=True)
                embed.add_field(name="Health", value=str(ball.health), inline=True)
                if ball.capacity_name:
                    embed.add_field(name="Capacity", value=ball.capacity_name, inline=True)
                embed.add_field(name="Tradeable", value="Yes" if ball.tradeable else "No", inline=True)
                if ball.capacity_description:
                    embed.add_field(name="Capacity Description", value=ball.capacity_description[:512], inline=False)
                if ball.credits:
                    embed.add_field(name="Art Credits", value=ball.credits, inline=True)
                if hasattr(ball, "cached_regime") and ball.cached_regime:
                    embed.add_field(name="Regime", value=ball.cached_regime.name, inline=True)
                if hasattr(ball, "cached_economy") and ball.cached_economy:
                    embed.add_field(name="Economy", value=ball.cached_economy.name, inline=True)

                await channel.create_thread(
                    name=ball.country[:100],
                    embed=embed,
                    file=dfile,
                    auto_archive_duration=10080,  # 7 days
                )
                posted += 1
                await asyncio.sleep(0.75)  # rate limit friendly

            except Exception:
                log.exception("Failed to create forum post for ball %r", getattr(ball, "country", "?"))
                failed += 1

        await interaction.followup.send(
            f"✅ Done — created **{posted}** posts, **{failed}** failed.",
            ephemeral=True,
        )

    @spawn.command(name="create", description="Post all spawn/wild art into a forum channel.")
    @app_commands.describe(channel="The forum channel to create posts in.")
    async def spawn_create(self, interaction: Interaction, channel: discord.ForumChannel) -> None:
        await self._create_forum_posts(
            interaction, channel,
            image_attr="wild_card",
            filename_suffix="spawn",
            embed_title_suffix="Spawn Art",
        )

    @card.command(name="create", description="Post all collection card art into a forum channel.")
    @app_commands.describe(channel="The forum channel to create posts in.")
    async def card_create(self, interaction: Interaction, channel: discord.ForumChannel) -> None:
        await self._create_forum_posts(
            interaction, channel,
            image_attr="collection_card",
            filename_suffix="card",
            embed_title_suffix="Collection Card",
        )


    async def _update_forum_posts(
        self,
        interaction: Interaction,
        channel: discord.ForumChannel,
        *,
        image_attr: str,
    ) -> None:
        """
        Walk every thread in the forum channel. If the attachment filename on the
        thread's first message no longer matches the ball's current art file, re-upload
        the new file. Threads whose ball no longer exists are skipped with a warning.
        """
        if not await is_staff(interaction):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        all_threads: set[discord.Thread] = set(channel.threads)
        async for thread in channel.archived_threads(limit=None):
            all_threads.add(thread)

        if not all_threads:
            await interaction.followup.send("No threads found in that channel.", ephemeral=True)
            return

        await interaction.followup.send(
            f"⏳ Checking **{len(all_threads)}** threads for outdated art…",
            ephemeral=True,
        )

        updated = 0
        skipped = 0
        failed = 0

        for thread in all_threads:
            try:
                try:
                    ball = await Ball.objects.aget(country=thread.name)
                except Ball.DoesNotExist:
                    log.debug("No ball found for thread %r — skipping.", thread.name)
                    skipped += 1
                    continue

                img_field = getattr(ball, image_attr, None)
                if not img_field or not img_field.name:
                    skipped += 1
                    continue

                try:
                    first_msg = await thread.fetch_message(thread.id)
                except discord.NotFound:
                    log.warning("Could not fetch first message for thread %r.", thread.name)
                    failed += 1
                    continue

                if not first_msg.attachments:
                    skipped += 1
                    continue

                current_filename = first_msg.attachments[0].filename
                expected_filename = os.path.basename(img_field.name)

                if current_filename == expected_filename:
                    continue

                file_path: str = img_field.path
                if not os.path.exists(file_path):
                    log.warning("Art file missing on disk for ball %r: %s", ball.country, file_path)
                    failed += 1
                    continue

                if thread.archived:
                    await thread.edit(archived=False)

                await first_msg.edit(
                    attachments=[discord.File(file_path, filename=expected_filename)]
                )
                updated += 1
                await asyncio.sleep(0.75)

            except Exception:
                log.exception("Error updating thread %r", getattr(thread, "name", "?"))
                failed += 1

        await interaction.followup.send(
            f"✅ Done — **{updated}** updated, **{skipped}** skipped (no change / no ball), "
            f"**{failed}** failed.",
            ephemeral=True,
        )

    @spawn.command(name="update", description="Update outdated spawn art in a forum channel.")
    @app_commands.describe(channel="The forum channel containing the spawn art threads.")
    async def spawn_update(self, interaction: Interaction, channel: discord.ForumChannel) -> None:
        await self._update_forum_posts(interaction, channel, image_attr="wild_card")

    @card.command(name="update", description="Update outdated collection card art in a forum channel.")
    @app_commands.describe(channel="The forum channel containing the card art threads.")
    async def card_update(self, interaction: Interaction, channel: discord.ForumChannel) -> None:
        await self._update_forum_posts(interaction, channel, image_attr="collection_card")


    async def _accept(
        self,
        interaction: Interaction,
        *,
        image_attr: str,
        link: str,
        index: int,
    ) -> None:
        """
        Accept a piece of art submitted in a forum thread via a message link.

        Steps:
        1. Resolve the message link → guild / thread / message.
        2. Validate the attachment index.
        3. Find the matching Ball by thread name.
        4. Save the attachment to disk using Django's storage.
        5. Update ball.<image_attr> in the database.
        6. React to the source message with the configured emoji.
        7. Optionally update the thread's first message with the new art.
        8. DM the artist with the configured accepted_message.
        9. Reply to the admin with a confirmation + preview.
        """
        if not await is_staff(interaction):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return

        if not link.startswith("https://discord.com/channels/"):
            await interaction.response.send_message(
                "Please provide a valid Discord message link "
                "(right-click a message → Copy Message Link).",
                ephemeral=True,
            )
            return

        parts = link.rstrip("/").split("/")
        if len(parts) < 7:
            await interaction.response.send_message("Could not parse message link.", ephemeral=True)
            return

        try:
            guild_id = int(parts[4])
            thread_id = int(parts[5])
            message_id = int(parts[6])
        except (ValueError, IndexError):
            await interaction.response.send_message(
                "Message link appears malformed.", ephemeral=True
            )
            return

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await interaction.response.send_message(
                "Could not find that server. Make sure the bot is in it.", ephemeral=True
            )
            return

        thread = guild.get_thread(thread_id)
        if thread is None:
            # Try fetching archived thread
            try:
                thread = await guild.fetch_channel(thread_id)  # type: ignore[assignment]
            except (discord.NotFound, discord.HTTPException):
                await interaction.response.send_message(
                    "Could not find that thread.", ephemeral=True
                )
                return

        try:
            message = await thread.fetch_message(message_id)
        except discord.NotFound:
            await interaction.response.send_message("Message not found.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"Failed to fetch message: {exc}", ephemeral=True
            )
            return

        attachment_index = index - 1
        if not message.attachments:
            await interaction.response.send_message(
                "That message has no attachments.", ephemeral=True
            )
            return
        if attachment_index < 0 or attachment_index >= len(message.attachments):
            await interaction.response.send_message(
                f"That message only has {len(message.attachments)} attachment(s); "
                f"index {index} is out of range.",
                ephemeral=True,
            )
            return

        attachment = message.attachments[attachment_index]

        try:
            ball = await Ball.objects.aget(country=thread.name)
        except Ball.DoesNotExist:
            await interaction.response.send_message(
                f"No ball named **{thread.name!r}** found. "
                "The thread name must exactly match a ball's country name.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        import re as _re
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        raw_bytes = await attachment.read()

        filename_re = _re.compile(r"^(.+?)(\.[^.]+)?$")
        match = filename_re.match(attachment.filename)
        stem = match.group(1) if match else attachment.filename
        ext = match.group(2) or ""
        upload_path = f"balls/{stem}{ext}"

        counter = 1
        candidate = upload_path
        while await sync_to_async(default_storage.exists)(candidate):
            candidate = f"balls/{stem}-{counter}{ext}"
            counter += 1

        saved_path = await sync_to_async(default_storage.save)(
            candidate, ContentFile(raw_bytes)
        )

        setattr(ball, image_attr, saved_path)
        await sync_to_async(ball.save)(update_fields=[image_attr])

        config = await ArtSettings.load()
        try:
            await message.add_reaction(config.accepted_emoji)
        except discord.HTTPException as exc:
            log.warning("Could not add reaction to accepted message: %s", exc)

        if config.update_thread_art:
            try:
                first_msg = await thread.fetch_message(thread.id)
                if thread.archived:
                    await thread.edit(archived=False)
                full_path = default_storage.path(saved_path)
                await first_msg.edit(
                    attachments=[discord.File(full_path, filename=os.path.basename(saved_path))]
                )
            except Exception:
                log.exception("Failed to update thread first message for %r", thread.name)

        dm_suffix = ""
        dm_text = (
            config.accepted_message
            .replace("$user", message.author.display_name)
            .replace("$ball", ball.country)
        )
        try:
            await message.author.send(dm_text)
        except discord.Forbidden:
            dm_suffix = "\n-# Could not DM the artist (DMs disabled)."
        except discord.HTTPException as exc:
            dm_suffix = f"\n-# DM failed: {exc}"

        full_path = default_storage.path(saved_path)
        await interaction.followup.send(
            f"✅ Accepted **{ball.country}** art by **{message.author.name}**.{dm_suffix}",
            file=discord.File(full_path, filename=os.path.basename(saved_path)),
            ephemeral=True,
        )

    @spawn.command(name="accept", description="Accept spawn art from a message link.")
    @app_commands.describe(
        link="Discord message link containing the spawn art.",
        index="Attachment number to use (default: 1).",
    )
    async def spawn_accept(
        self, interaction: Interaction, link: str, index: int = 1
    ) -> None:
        await self._accept(interaction, image_attr="wild_card", link=link, index=index)

    @card.command(name="accept", description="Accept collection card art from a message link.")
    @app_commands.describe(
        link="Discord message link containing the card art.",
        index="Attachment number to use (default: 1).",
    )
    async def card_accept(
        self, interaction: Interaction, link: str, index: int = 1
    ) -> None:
        await self._accept(interaction, image_attr="collection_card", link=link, index=index)
