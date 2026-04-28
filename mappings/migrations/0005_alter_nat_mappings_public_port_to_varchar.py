from django.db import migrations


def alter_public_port_to_varchar(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "mysql":
        table_names = set(schema_editor.connection.introspection.table_names())
        if "nat_mappings" not in table_names:
            return

        with schema_editor.connection.cursor() as cursor:
            columns = {
                column.name
                for column in schema_editor.connection.introspection.get_table_description(cursor, "nat_mappings")
            }
        if "public_port" not in columns:
            return

        schema_editor.execute(
            """
            ALTER TABLE `nat_mappings`
            MODIFY COLUMN `public_port` varchar(20) NOT NULL COMMENT '公网端口（支持数字或服务名）';
            """
        )
    elif vendor == "sqlite":
        # SQLite: keep as-is in dev fallback; production path is MySQL.
        return


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("mappings", "0004_alter_portmapping_options"),
    ]

    operations = [
        migrations.RunPython(alter_public_port_to_varchar, migrations.RunPython.noop),
    ]
