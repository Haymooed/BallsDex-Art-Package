from __future__ import annotations

from django.core.validators import URLValidator
from django.db import models
from django.utils import timezone

from bd_models.models import Ball, Player


class ArtStatus(models.TextChoices):
    """Status choices for art entries."""

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ArtSettings(models.Model):
    """Singleton configuration for art submission behaviour."""

    enabled = models.BooleanField(
        default=True, help_text="Globally enable art submission and viewing commands"
    )
    require_approval = models.BooleanField(
        default=True, help_text="If enabled, art submissions require admin approval before being visible"
    )
    max_submissions_per_day = models.PositiveIntegerField(
        default=5, help_text="Maximum number of art submissions per player per day"
    )

    class Meta:
        verbose_name = "Art Settings"

    def __str__(self) -> str:
        return "Art Settings"

    @classmethod
    def get_solo(cls) -> "ArtSettings":
        """
        Lightweight replacement for django-solo's get_solo().

        Ensures there is always exactly one settings row.
        """
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ArtEntry(models.Model):
    """Art submission entry linked to a ball and player."""

    # Relationships
    ball = models.ForeignKey(
        Ball,
        on_delete=models.CASCADE,
        related_name="art_entries",
        help_text="Ball this artwork is associated with.",
    )
    artist = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="art_submissions",
        help_text="Player who submitted this artwork.",
    )

    # Art content
    title = models.CharField(
        max_length=256,
        blank=True,
        help_text="Optional title for the artwork.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of the artwork.",
    )
    media_url = models.URLField(
        max_length=2048,
        validators=[URLValidator()],
        help_text="URL to the artwork (image, video, etc.).",
    )

    # Status and moderation
    status = models.CharField(
        max_length=20,
        choices=ArtStatus.choices,
        default=ArtStatus.PENDING,
        help_text="Current approval status of the art entry.",
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if rejected).",
    )
    reviewed_by = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_art_entries",
        help_text="Admin who reviewed this entry.",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this entry was reviewed.",
    )

    # Visibility
    enabled = models.BooleanField(
        default=True,
        help_text="If disabled, this art entry will not be shown to players.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Art Entry"
        verbose_name_plural = "Art Entries"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["ball", "status", "enabled"]),
            models.Index(fields=["artist", "status"]),
        ]

    def __str__(self) -> str:
        status_display = self.get_status_display()
        ball_name = self.ball.country if self.ball else "Unknown"
        title = self.title or "Untitled"
        return f"{title} ({ball_name}) - {status_display}"

    def approve(self, reviewer: Player) -> None:
        """Approve this art entry."""
        self.status = ArtStatus.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])

    def reject(self, reviewer: Player, reason: str = "") -> None:
        """Reject this art entry."""
        self.status = ArtStatus.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])
