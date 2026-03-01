from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("bd_models", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArtSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=True, help_text="Globally enable or disable art submission and viewing commands.")),
                ("require_approval", models.BooleanField(default=True, help_text="When enabled, submissions start as Pending and require admin review. When disabled, submissions are immediately Approved.")),
                ("max_submissions_per_day", models.PositiveIntegerField(default=5, help_text="Maximum number of art submissions per player per day.")),
            ],
            options={"verbose_name": "Art Settings"},
        ),
        migrations.CreateModel(
            name="ArtEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, help_text="Optional display title for the artwork.", max_length=256)),
                ("description", models.TextField(blank=True, help_text="Optional description of the artwork.")),
                (
                    "media_url",
                    models.URLField(
                        help_text="Direct URL to the artwork (image, video, etc.).",
                        max_length=2048,
                        validators=[django.core.validators.URLValidator()],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
                        default="pending",
                        help_text="Current approval status.",
                        max_length=20,
                    ),
                ),
                ("rejection_reason", models.TextField(blank=True, help_text="Reason provided when this entry was rejected.")),
                ("enabled", models.BooleanField(default=True, help_text="Hidden entries are not shown to players even if Approved.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reviewed_at", models.DateTimeField(blank=True, help_text="Timestamp of when this entry was reviewed.", null=True)),
                (
                    "artist",
                    models.ForeignKey(
                        help_text="The player who submitted this artwork.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="art_submissions",
                        to="bd_models.player",
                    ),
                ),
                (
                    "ball",
                    models.ForeignKey(
                        help_text="The ball this artwork is associated with.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="art_entries",
                        to="bd_models.ball",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Admin player who reviewed this entry.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_art_entries",
                        to="bd_models.player",
                    ),
                ),
            ],
            options={
                "verbose_name": "Art Entry",
                "verbose_name_plural": "Art Entries",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="artentry",
            index=models.Index(fields=["ball", "status", "enabled"], name="art_ball_status_enabled_idx"),
        ),
        migrations.AddIndex(
            model_name="artentry",
            index=models.Index(fields=["artist", "created_at"], name="art_artist_created_idx"),
        ),
    ]
