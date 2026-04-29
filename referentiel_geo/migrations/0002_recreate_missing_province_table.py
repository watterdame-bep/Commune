from django.db import migrations


def recreate_province_table_if_missing(apps, schema_editor):
    """
    Le dernier refactor a déclenché une migration qui a partiellement supprimé des tables.
    On recrée uniquement la table `accounts_province` si elle manque, sans toucher au reste.
    """
    table_name = "accounts_province"
    existing_tables = schema_editor.connection.introspection.table_names()
    if table_name in existing_tables:
        return

    Province = apps.get_model("referentiel_geo", "Province")
    schema_editor.create_model(Province)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("referentiel_geo", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(recreate_province_table_if_missing, reverse_code=migrations.RunPython.noop),
    ]

