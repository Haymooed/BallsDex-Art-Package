from __future__ import annotations

from django.core.validators import URLValidator
from django.db import models
from django.utils import timezone

from bd_models.models import Ball, Player


class ArtStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ArtSettings(models.Model):
    """Singleton configuration for the art system."""

    enabled = models.BooleanField(
        default=True,
        help_text="Globally enable or disable art submission and viewing commands.",
    )
    require_approval = models.BooleanField(
        default=True,
        help_text=(
            "When enabled, submissions start as Pending and require admin review. "
            "When disabled, submissions are immediately Approved."
        ),
    )
    max_submissions_per_day = models.PositiveIntegerField(
        default=5,
        help_text="Maximum number of art submissions per player per day.",
    )


    accepted_message = models.TextField(
        default="Hi $user, your artwork for **$ball** has been accepted!",
        help_text=(
            "DM sent to the artist when their art is accepted via /art spawn accept or /art card accept. "
            "Use $user for the artist's display name and $ball for the ball name."
        ),
    )
    accepted_emoji = models.CharField(
        max_length=64,
        default="✅",
        help_text=(
            "Emoji reacted to the source message when art is accepted. "
            "Use a Unicode emoji (e.g. ✅) or a custom emoji string (e.g. <:name:id>)."
        ),
    )
    update_thread_art = models.BooleanField(
        default=True,
        help_text=(
            "When enabled, accepting art via /art spawn accept or /art card accept will also "
            "update the first message in the corresponding forum thread to show the new art."
        ),
    )
    safe_threads = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Comma-separated list of thread names that should never be deleted during "
            "/art spawn create or /art card create (e.g. 'Pinned,Guidelines,Welcome')."
        ),
    )

    @property
    def safe_thread_names(self) -> list[str]:
        """Return safe_threads as a list of stripped names."""
        return [s.strip() for s in self.safe_threads.split(",") if s.strip()]

    class Meta:
        verbose_name = "Art Settings"

    def __str__(self) -> str:
        return "Art Settings"

    @classmethod
    async def load(cls) -> "ArtSettings":
        """Return the singleton settings row, creating it with defaults if absent."""
        obj, _ = await cls.objects.aget_or_create(pk=1)
        return obj


class ArtEntry(models.Model):
    """A single artwork submission linked to a ball and a player."""

    ball = models.ForeignKey(
        Ball,
        on_delete=models.CASCADE,
        related_name="art_entries",
        help_text="The ball this artwork is associated with.",
    )
    artist = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="art_submissions",
        help_text="The player who submitted this artwork.",
    )
    title = models.CharField(
        max_length=256,
        blank=True,
        help_text="Optional display title for the artwork.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of the artwork.",
    )
    media_url = models.URLField(
        max_length=2048,
        validators=[URLValidator()],
        help_text="Direct URL to the artwork (image, video, etc.).",
    )

    # Moderation
    status = models.CharField(
        max_length=20,
        choices=ArtStatus.choices,
        default=ArtStatus.PENDING,
        help_text="Current approval status.",
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason provided when this entry was rejected.",
    )
    reviewed_by = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_art_entries",
        help_text="Admin player who reviewed this entry.",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of when this entry was reviewed.",
    )

    # Visibility
    enabled = models.BooleanField(
        default=True,
        help_text="Hidden entries are not shown to players even if Approved.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Art Entry"
        verbose_name_plural = "Art Entries"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["ball", "status", "enabled"], name="art_ball_status_enabled_idx"),
            models.Index(fields=["artist", "created_at"], name="art_artist_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title or 'Untitled'} ({self.ball_id}) [{self.get_status_display()}]"


    def approve(self, reviewer: Player) -> None:
        self.status = ArtStatus.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])

    def reject(self, reviewer: Player, reason: str = "") -> None:
        self.status = ArtStatus.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])

    @property
    def display_title(self) -> str:
        return self.title or "Untitled"

    def is_image_url(self) -> bool:
        return any(
            self.media_url.lower().endswith(ext)
            for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")
        )
