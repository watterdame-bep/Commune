# Generated manually for SI-SEP-Commune

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_demande"),
    ]

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titre", models.CharField(max_length=200)),
                ("fichier", models.FileField(upload_to="documents/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "demande",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="accounts.demande",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
    ]

