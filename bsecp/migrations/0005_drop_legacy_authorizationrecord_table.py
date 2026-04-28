from django.db import migrations


def drop_legacy_table(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == "mysql":
            cursor.execute("DROP TABLE IF EXISTS `bsecp_authorizationrecord`;")
        elif vendor == "sqlite":
            cursor.execute('DROP TABLE IF EXISTS "bsecp_authorizationrecord";')


class Migration(migrations.Migration):
    dependencies = [
        ("bsecp", "0004_sync_order_auto_authorization_queue"),
    ]

    operations = [
        migrations.RunPython(drop_legacy_table, migrations.RunPython.noop),
    ]

