from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("art", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="artsettings",
            name="accepted_message",
            field=models.TextField(
                default="Hi $user, your artwork for **$ball** has been accepted!",
                help_text=(
                    "DM sent to the artist when their art is accepted via /art spawn accept or "
                    "/art card accept. Use $user for the artist's display name and $ball for the ball name."
                ),
            ),
        ),
        migrations.AddField(
            model_name="artsettings",
            name="accepted_emoji",
            field=models.CharField(
                default="✅",
                max_length=64,
                help_text=(
                    "Emoji reacted to the source message when art is accepted. "
                    "Use a Unicode emoji (e.g. ✅) or a custom emoji string (e.g. <:name:id>)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="artsettings",
            name="update_thread_art",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When enabled, accepting art via /art spawn accept or /art card accept will "
                    "also update the first message in the corresponding forum thread."
                ),
            ),
        ),
        migrations.AddField(
            model_name="artsettings",
            name="safe_threads",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Comma-separated list of thread names that should never be deleted during "
                    "/art spawn create or /art card create (e.g. 'Pinned,Guidelines,Welcome')."
                ),
            ),
        ),
    ]
