from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_rename_passwordresetcode_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="Commune",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nom", models.CharField(max_length=120, unique=True)),
                ("province", models.CharField(blank=True, default="", max_length=120)),
                ("code", models.CharField(blank=True, db_index=True, default="", max_length=32)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("nom",),
            },
        ),
    ]

