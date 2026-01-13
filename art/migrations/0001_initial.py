from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("bd_models", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArtSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Globally enable art submission and viewing commands",
                    ),
                ),
                (
                    "require_approval",
                    models.BooleanField(
                        default=True,
                        help_text="If enabled, art submissions require admin approval before being visible",
                    ),
                ),
                (
                    "max_submissions_per_day",
                    models.PositiveIntegerField(
                        default=5, help_text="Maximum number of art submissions per player per day"
                    ),
                ),
            ],
            options={
                "verbose_name": "Art Settings",
            },
        ),
        migrations.CreateModel(
            name="ArtEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        blank=True, help_text="Optional title for the artwork.", max_length=256
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, help_text="Optional description of the artwork."),
                ),
                (
                    "media_url",
                    models.URLField(
                        help_text="URL to the artwork (image, video, etc.).",
                        max_length=2048,
                        validators=[django.core.validators.URLValidator()],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        help_text="Current approval status of the art entry.",
                        max_length=20,
                    ),
                ),
                (
                    "rejection_reason",
                    models.TextField(blank=True, help_text="Reason for rejection (if rejected)."),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text="If disabled, this art entry will not be shown to players.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reviewed_at",
                    models.DateTimeField(
                        blank=True, help_text="When this entry was reviewed.", null=True
                    ),
                ),
                (
                    "ball",
                    models.ForeignKey(
                        help_text="Ball this artwork is associated with.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="art_entries",
                        to="bd_models.ball",
                    ),
                ),
                (
                    "artist",
                    models.ForeignKey(
                        help_text="Player who submitted this artwork.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="art_submissions",
                        to="bd_models.player",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Admin who reviewed this entry.",
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
            index=models.Index(
                fields=["ball", "status", "enabled"], name="art_artentr_ball_id_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="artentry",
            index=models.Index(
                fields=["artist", "status"], name="art_artentr_artist__status_idx"
            ),
        ),
    ]
