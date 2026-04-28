from django.db import migrations, models


def create_bseip_and_drop_legacy(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == "mysql":
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS `bseip` (
                  `id` int NOT NULL AUTO_INCREMENT,
                  `命名空间` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `空间归属` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `申请部门` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `空间对接人` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `服务工程师` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `开通日期` date NULL DEFAULT NULL,
                  `到期日期` date NULL DEFAULT NULL,
                  `用途` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `是否停用` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  PRIMARY KEY (`id`) USING BTREE
                ) ENGINE=InnoDB AUTO_INCREMENT=2629 CHARACTER SET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC
                """
            )
            cursor.execute("DROP TABLE IF EXISTS `assets_namespace`")
        elif vendor == "sqlite":
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS "bseip" (
                  "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                  "命名空间" varchar(50) NULL,
                  "空间归属" varchar(50) NULL,
                  "申请部门" varchar(50) NULL,
                  "空间对接人" varchar(50) NULL,
                  "服务工程师" varchar(50) NULL,
                  "开通日期" date NULL,
                  "到期日期" date NULL,
                  "用途" varchar(50) NULL,
                  "是否停用" varchar(50) NULL
                )
                """
            )
            cursor.execute('DROP TABLE IF EXISTS "assets_namespace"')
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bseip (
                  id integer NOT NULL PRIMARY KEY,
                  "命名空间" varchar(50) NULL,
                  "空间归属" varchar(50) NULL,
                  "申请部门" varchar(50) NULL,
                  "空间对接人" varchar(50) NULL,
                  "服务工程师" varchar(50) NULL,
                  "开通日期" date NULL,
                  "到期日期" date NULL,
                  "用途" varchar(50) NULL,
                  "是否停用" varchar(50) NULL
                )
                """
            )
            cursor.execute("DROP TABLE IF EXISTS assets_namespace")


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0002_physicalhost_xenserver"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    create_bseip_and_drop_legacy,
                    reverse_code=migrations.RunPython.noop,
                )
            ],
            state_operations=[
                migrations.DeleteModel(
                    name="Namespace",
                ),
                migrations.CreateModel(
                    name="Namespace",
                    fields=[
                        ("id", models.AutoField(primary_key=True, serialize=False, verbose_name="ID")),
                        ("namespace_name", models.CharField(blank=True, db_column="命名空间", max_length=50, null=True, verbose_name="命名空间")),
                        ("space_owner", models.CharField(blank=True, db_column="空间归属", max_length=50, null=True, verbose_name="空间归属")),
                        ("request_department", models.CharField(blank=True, db_column="申请部门", max_length=50, null=True, verbose_name="申请部门")),
                        ("space_contact", models.CharField(blank=True, db_column="空间对接人", max_length=50, null=True, verbose_name="空间对接人")),
                        ("service_engineer", models.CharField(blank=True, db_column="服务工程师", max_length=50, null=True, verbose_name="服务工程师")),
                        ("open_date", models.DateField(blank=True, db_column="开通日期", null=True, verbose_name="开通日期")),
                        ("expiry_date", models.DateField(blank=True, db_column="到期日期", null=True, verbose_name="到期日期")),
                        ("purpose", models.CharField(blank=True, db_column="用途", max_length=50, null=True, verbose_name="用途")),
                        ("disabled", models.CharField(blank=True, db_column="是否停用", max_length=50, null=True, verbose_name="是否停用")),
                    ],
                    options={
                        "verbose_name": "NameSpace",
                        "verbose_name_plural": "NameSpace",
                        "db_table": "bseip",
                        "ordering": ["-id"],
                    },
                ),
            ],
        ),
    ]
