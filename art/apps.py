from django.apps import AppConfig


class ArtConfig(AppConfig):
    """Django app configuration for the art package."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "art"
    verbose_name = "Art"
    dpy_package = "art.package"  # Path to the discord.py extension
