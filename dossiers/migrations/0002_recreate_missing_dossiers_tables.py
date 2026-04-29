from django.db import migrations


def recreate_missing_tables_if_needed(apps, schema_editor):
    """
    Répare un état DB après un refactor migrationnel raté :
    recrée uniquement les tables absentes côté MySQL.
    """
    tables_to_models = [
        ("accounts_demande", ("dossiers", "Demande")),
        ("accounts_document", ("dossiers", "Document")),
        ("accounts_galleryphoto", ("dossiers", "GalleryPhoto")),
    ]

    existing_tables = set(schema_editor.connection.introspection.table_names())

    # Ordre important: Demande -> Document
    for table_name, (app_label, model_name) in tables_to_models:
        if table_name in existing_tables:
            continue
        Model = apps.get_model(app_label, model_name)
        schema_editor.create_model(Model)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("dossiers", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(recreate_missing_tables_if_needed, reverse_code=migrations.RunPython.noop),
    ]

