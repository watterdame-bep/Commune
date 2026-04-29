from django.db import migrations


def add_galleryphoto_ville_if_missing(apps, schema_editor):
    """
    Ajoute la colonne ville_id à accounts_galleryphoto si elle n'existe pas.
    On évite les contraintes FK (db_constraint=False côté modèle) pour rester
    compatible avec les bases existantes.
    """
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'accounts_galleryphoto'
              AND COLUMN_NAME = 'ville_id'
            """
        )
        exists = int(cursor.fetchone()[0] or 0) > 0
        if not exists:
            cursor.execute("ALTER TABLE accounts_galleryphoto ADD COLUMN ville_id BIGINT NULL")
            cursor.execute("CREATE INDEX accounts_galleryphoto_ville_id_idx ON accounts_galleryphoto (ville_id)")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("dossiers", "0002_recreate_missing_dossiers_tables"),
    ]

    operations = [
        migrations.RunPython(add_galleryphoto_ville_if_missing, migrations.RunPython.noop),
    ]

