from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import ArtEntry, ArtSettings, ArtStatus


@admin.register(ArtSettings)
class ArtSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Status", {"fields": ("enabled",)}),
        (
            "Submissions",
            {"fields": ("require_approval", "max_submissions_per_day")},
        ),
        (
            "Accept Command",
            {
                "fields": ("accepted_message", "accepted_emoji", "update_thread_art"),
                "description": (
                    "Settings used by /art spawn accept and /art card accept. "
                    "accepted_message supports $user and $ball placeholders."
                ),
            },
        ),
        (
            "Forum Utilities",
            {
                "fields": ("safe_threads",),
                "description": (
                    "Comma-separated thread names that will never be deleted "
                    "when running /art spawn create or /art card create."
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        if ArtSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ArtEntry)
class ArtEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title_display",
        "ball",
        "artist",
        "status_badge",
        "enabled",
        "created_at",
    )
    list_filter = ("status", "enabled", "ball")
    search_fields = ("title", "description", "ball__country", "artist__discord_id")
    readonly_fields = ("created_at", "updated_at", "reviewed_at", "media_preview")
    autocomplete_fields = ("ball", "artist", "reviewed_by")
    date_hierarchy = "created_at"
    actions = ["action_approve", "action_reject"]

    fieldsets = (
        (
            "Artwork",
            {"fields": ("ball", "artist", "title", "description", "media_url", "media_preview")},
        ),
        (
            "Moderation",
            {"fields": ("status", "enabled", "rejection_reason", "reviewed_by", "reviewed_at")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    @admin.display(description="Title")
    def title_display(self, obj: ArtEntry) -> str:
        return obj.display_title

    @admin.display(description="Status")
    def status_badge(self, obj: ArtEntry) -> str:
        colors = {
            ArtStatus.PENDING: "#e67e22",
            ArtStatus.APPROVED: "#27ae60",
            ArtStatus.REJECTED: "#e74c3c",
        }
        color = colors.get(obj.status, "#95a5a6")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:3px;'
            'font-weight:bold;font-size:0.85em">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Media Preview")
    def media_preview(self, obj: ArtEntry) -> str:
        if not obj.media_url:
            return "—"
        if obj.is_image_url():
            return format_html(
                '<a href="{url}" target="_blank">'
                '<img src="{url}" style="max-height:120px;max-width:240px;border-radius:4px"/>'
                "</a>",
                url=obj.media_url,
            )
        return format_html('<a href="{}" target="_blank">View Media ↗</a>', obj.media_url)

    @admin.action(description="✅ Approve selected art entries")
    def action_approve(self, request, queryset):
        from bd_models.models import Player

        try:
            reviewer = Player.objects.get(discord_id=getattr(request.user, "discord_user_id", None))
        except (Player.DoesNotExist, TypeError, AttributeError):
            # Fall back to a sentinel reviewer if none is found
            reviewer = None

        count = 0
        for entry in queryset.exclude(status=ArtStatus.APPROVED):
            if reviewer:
                entry.approve(reviewer)
            else:
                from django.utils import timezone
                entry.status = ArtStatus.APPROVED
                entry.reviewed_at = timezone.now()
                entry.rejection_reason = ""
                entry.save(update_fields=["status", "reviewed_at", "rejection_reason", "updated_at"])
            count += 1
        self.message_user(request, f"Approved {count} art entr{'y' if count == 1 else 'ies'}.")

    @admin.action(description="❌ Reject selected art entries")
    def action_reject(self, request, queryset):
        from bd_models.models import Player

        try:
            reviewer = Player.objects.get(discord_id=getattr(request.user, "discord_user_id", None))
        except (Player.DoesNotExist, TypeError, AttributeError):
            reviewer = None

        count = 0
        for entry in queryset.exclude(status=ArtStatus.REJECTED):
            if reviewer:
                entry.reject(reviewer, "Bulk rejected via admin panel")
            else:
                from django.utils import timezone
                entry.status = ArtStatus.REJECTED
                entry.reviewed_at = timezone.now()
                entry.rejection_reason = "Bulk rejected via admin panel"
                entry.save(update_fields=["status", "reviewed_at", "rejection_reason", "updated_at"])
            count += 1
        self.message_user(request, f"Rejected {count} art entr{'y' if count == 1 else 'ies'}.")
