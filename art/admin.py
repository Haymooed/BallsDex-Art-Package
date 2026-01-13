from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.utils.html import format_html

from .models import ArtEntry, ArtSettings, ArtStatus

if TYPE_CHECKING:
    from django.db.models import QuerySet


@admin.register(ArtSettings)
class ArtSettingsAdmin(admin.ModelAdmin):
    """Singleton-style admin for art settings."""

    fieldsets = (
        (
            "Status",
            {"fields": ("enabled",)},
        ),
        (
            "Behaviour",
            {
                "fields": (
                    "require_approval",
                    "max_submissions_per_day",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        # Only allow a single settings row
        if ArtSettings.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(ArtEntry)
class ArtEntryAdmin(admin.ModelAdmin):
    """Admin configuration for art entries."""

    list_display = (
        "id",
        "title_display",
        "ball",
        "artist",
        "status_badge",
        "enabled",
        "created_at",
    )
    list_filter = ("status", "enabled", "created_at", "ball")
    search_fields = ("title", "description", "ball__country", "artist__discord_id")
    readonly_fields = (
        "created_at",
        "updated_at",
        "reviewed_at",
        "media_preview",
    )
    autocomplete_fields = ("ball", "artist", "reviewed_by")
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Art Information",
            {
                "fields": (
                    "ball",
                    "artist",
                    "title",
                    "description",
                    "media_url",
                    "media_preview",
                )
            },
        ),
        (
            "Status & Moderation",
            {
                "fields": (
                    "status",
                    "enabled",
                    "rejection_reason",
                    "reviewed_by",
                    "reviewed_at",
                )
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    actions = ["approve_selected", "reject_selected"]

    @admin.display(description="Title")
    def title_display(self, obj: ArtEntry) -> str:
        """Display title or 'Untitled'."""
        return obj.title or "Untitled"

    @admin.display(description="Status")
    def status_badge(self, obj: ArtEntry) -> str:
        """Display status with color coding."""
        colors = {
            ArtStatus.PENDING: "orange",
            ArtStatus.APPROVED: "green",
            ArtStatus.REJECTED: "red",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Media Preview")
    def media_preview(self, obj: ArtEntry) -> str:
        """Display a preview link for the media URL."""
        if obj.media_url:
            return format_html(
                '<a href="{}" target="_blank">View Media</a>',
                obj.media_url,
            )
        return "No media URL"

    @admin.action(description="Approve selected art entries")
    def approve_selected(self, request, queryset: "QuerySet[ArtEntry]"):
        """Bulk approve action."""
        from bd_models.models import Player

        try:
            reviewer = Player.objects.get(discord_id=request.user.discord_user_id)
        except (Player.DoesNotExist, AttributeError):
            self.message_user(request, "Could not find reviewer player. Approval failed.", level="error")
            return

        count = 0
        for entry in queryset.filter(status=ArtStatus.PENDING):
            entry.approve(reviewer)
            count += 1

        self.message_user(request, f"Successfully approved {count} art entries.")

    @admin.action(description="Reject selected art entries")
    def reject_selected(self, request, queryset: "QuerySet[ArtEntry]"):
        """Bulk reject action."""
        from bd_models.models import Player

        try:
            reviewer = Player.objects.get(discord_id=request.user.discord_user_id)
        except (Player.DoesNotExist, AttributeError):
            self.message_user(request, "Could not find reviewer player. Rejection failed.", level="error")
            return

        count = 0
        for entry in queryset.filter(status=ArtStatus.PENDING):
            entry.reject(reviewer, "Bulk rejected via admin panel")
            count += 1

        self.message_user(request, f"Successfully rejected {count} art entries.")
