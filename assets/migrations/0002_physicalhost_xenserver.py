from django.db import migrations, models


def create_xenserver_and_drop_legacy(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == "mysql":
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS `xenserver` (
                  `id` int NOT NULL AUTO_INCREMENT,
                  `服务器IP` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `型号` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `购买途径` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `购买日期` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `端口` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `登录密码` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `内存` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `磁盘` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `硬盘类型` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `内存已使用` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `磁盘已使用` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `内存剩余` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `磁盘剩余` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `剩余可开` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `部门` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `用途` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  PRIMARY KEY (`id`) USING BTREE
                ) ENGINE=InnoDB AUTO_INCREMENT=101 CHARACTER SET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC
                """
            )
            cursor.execute("DROP TABLE IF EXISTS `assets_physicalhost`")
        elif vendor == "sqlite":
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS "xenserver" (
                  "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                  "服务器IP" varchar(50) NULL,
                  "型号" varchar(50) NULL,
                  "购买途径" varchar(50) NULL,
                  "购买日期" varchar(50) NULL,
                  "端口" varchar(50) NULL,
                  "登录密码" varchar(50) NULL,
                  "内存" varchar(50) NULL,
                  "磁盘" varchar(50) NULL,
                  "硬盘类型" varchar(50) NULL,
                  "内存已使用" varchar(50) NULL,
                  "磁盘已使用" varchar(50) NULL,
                  "内存剩余" varchar(50) NULL,
                  "磁盘剩余" varchar(50) NULL,
                  "剩余可开" varchar(50) NULL,
                  "部门" varchar(50) NULL,
                  "用途" varchar(50) NULL
                )
                """
            )
            cursor.execute('DROP TABLE IF EXISTS "assets_physicalhost"')
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS xenserver (
                  id integer NOT NULL PRIMARY KEY,
                  "服务器IP" varchar(50) NULL,
                  "型号" varchar(50) NULL,
                  "购买途径" varchar(50) NULL,
                  "购买日期" varchar(50) NULL,
                  "端口" varchar(50) NULL,
                  "登录密码" varchar(50) NULL,
                  "内存" varchar(50) NULL,
                  "磁盘" varchar(50) NULL,
                  "硬盘类型" varchar(50) NULL,
                  "内存已使用" varchar(50) NULL,
                  "磁盘已使用" varchar(50) NULL,
                  "内存剩余" varchar(50) NULL,
                  "磁盘剩余" varchar(50) NULL,
                  "剩余可开" varchar(50) NULL,
                  "部门" varchar(50) NULL,
                  "用途" varchar(50) NULL
                )
                """
            )
            cursor.execute("DROP TABLE IF EXISTS assets_physicalhost")


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    create_xenserver_and_drop_legacy,
                    reverse_code=migrations.RunPython.noop,
                )
            ],
            state_operations=[
                migrations.DeleteModel(
                    name="PhysicalHost",
                ),
                migrations.CreateModel(
                    name="PhysicalHost",
                    fields=[
                        ("id", models.AutoField(primary_key=True, serialize=False, verbose_name="ID")),
                        ("server_ip", models.CharField(blank=True, db_column="服务器IP", max_length=50, null=True, verbose_name="服务器IP")),
                        ("model_name", models.CharField(blank=True, db_column="型号", max_length=50, null=True, verbose_name="型号")),
                        ("purchase_channel", models.CharField(blank=True, db_column="购买途径", max_length=50, null=True, verbose_name="购买途径")),
                        ("purchase_date", models.CharField(blank=True, db_column="购买日期", max_length=50, null=True, verbose_name="购买日期")),
                        ("port", models.CharField(blank=True, db_column="端口", max_length=50, null=True, verbose_name="端口")),
                        ("login_password", models.CharField(blank=True, db_column="登录密码", max_length=50, null=True, verbose_name="登录密码")),
                        ("memory", models.CharField(blank=True, db_column="内存", max_length=50, null=True, verbose_name="内存")),
                        ("disk", models.CharField(blank=True, db_column="磁盘", max_length=50, null=True, verbose_name="磁盘")),
                        ("disk_type", models.CharField(blank=True, db_column="硬盘类型", max_length=50, null=True, verbose_name="硬盘类型")),
                        ("memory_used", models.CharField(blank=True, db_column="内存已使用", max_length=50, null=True, verbose_name="内存已使用")),
                        ("disk_used", models.CharField(blank=True, db_column="磁盘已使用", max_length=50, null=True, verbose_name="磁盘已使用")),
                        ("memory_remaining", models.CharField(blank=True, db_column="内存剩余", max_length=50, null=True, verbose_name="内存剩余")),
                        ("disk_remaining", models.CharField(blank=True, db_column="磁盘剩余", max_length=50, null=True, verbose_name="磁盘剩余")),
                        ("remaining_capacity", models.CharField(blank=True, db_column="剩余可开", max_length=50, null=True, verbose_name="剩余可开")),
                        ("department", models.CharField(blank=True, db_column="部门", max_length=50, null=True, verbose_name="部门")),
                        ("purpose", models.CharField(blank=True, db_column="用途", max_length=50, null=True, verbose_name="用途")),
                    ],
                    options={
                        "verbose_name": "物理机",
                        "verbose_name_plural": "物理机",
                        "db_table": "xenserver",
                        "ordering": ["-id"],
                    },
                ),
            ],
        ),
    ]
