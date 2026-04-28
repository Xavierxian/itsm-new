from django.db import migrations, models


def create_cljc_module_and_drop_legacy(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == "mysql":
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS `cljc_module` (
                  `MD_ID` int NOT NULL AUTO_INCREMENT,
                  `MD_CODE` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
                  `MD_NAME` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
                  `MD_PRODUCTID` int NOT NULL,
                  `MD_PRODUCTCODE` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `MD_ISPOINT` int NOT NULL,
                  `MD_PRICE` decimal(18,2) NOT NULL,
                  `MD_STATE` int NULL DEFAULT NULL,
                  `MD_REMARK` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `MD_FORBIT_DATE` datetime NULL DEFAULT NULL,
                  `MD_FORBIT_ID` int NULL DEFAULT NULL,
                  `MD_FORBIT_USER` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `MD_CREATE_DATE` datetime NULL DEFAULT NULL,
                  `MD_CREATE_ID` int NULL DEFAULT NULL,
                  `MD_CREATE_USER` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  `MD_MODIFY_DATE` datetime NULL DEFAULT NULL,
                  `MD_MODIFY_ID` int NULL DEFAULT NULL,
                  `MD_MODIFY_USER` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
                  PRIMARY KEY (`MD_ID`) USING BTREE
                ) ENGINE=InnoDB AUTO_INCREMENT=248 CHARACTER SET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC
                """
            )
            cursor.execute("DROP TABLE IF EXISTS `bsecp_module`")
        elif vendor == "sqlite":
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS "cljc_module" (
                  "MD_ID" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                  "MD_CODE" varchar(50) NOT NULL,
                  "MD_NAME" varchar(200) NOT NULL,
                  "MD_PRODUCTID" integer NOT NULL,
                  "MD_PRODUCTCODE" varchar(50) NULL,
                  "MD_ISPOINT" integer NOT NULL,
                  "MD_PRICE" decimal(18,2) NOT NULL,
                  "MD_STATE" integer NULL,
                  "MD_REMARK" varchar(100) NULL,
                  "MD_FORBIT_DATE" datetime NULL,
                  "MD_FORBIT_ID" integer NULL,
                  "MD_FORBIT_USER" varchar(50) NULL,
                  "MD_CREATE_DATE" datetime NULL,
                  "MD_CREATE_ID" integer NULL,
                  "MD_CREATE_USER" varchar(50) NULL,
                  "MD_MODIFY_DATE" datetime NULL,
                  "MD_MODIFY_ID" integer NULL,
                  "MD_MODIFY_USER" varchar(50) NULL
                )
                """
            )
            cursor.execute('DROP TABLE IF EXISTS "bsecp_module"')
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cljc_module (
                  MD_ID integer NOT NULL PRIMARY KEY,
                  MD_CODE varchar(50) NOT NULL,
                  MD_NAME varchar(200) NOT NULL,
                  MD_PRODUCTID integer NOT NULL,
                  MD_PRODUCTCODE varchar(50) NULL,
                  MD_ISPOINT integer NOT NULL,
                  MD_PRICE decimal(18,2) NOT NULL,
                  MD_STATE integer NULL,
                  MD_REMARK varchar(100) NULL,
                  MD_FORBIT_DATE datetime NULL,
                  MD_FORBIT_ID integer NULL,
                  MD_FORBIT_USER varchar(50) NULL,
                  MD_CREATE_DATE datetime NULL,
                  MD_CREATE_ID integer NULL,
                  MD_CREATE_USER varchar(50) NULL,
                  MD_MODIFY_DATE datetime NULL,
                  MD_MODIFY_ID integer NULL,
                  MD_MODIFY_USER varchar(50) NULL
                )
                """
            )
            cursor.execute("DROP TABLE IF EXISTS bsecp_module")


class Migration(migrations.Migration):
    dependencies = [
        ("bsecp", "0005_drop_legacy_authorizationrecord_table"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    create_cljc_module_and_drop_legacy,
                    reverse_code=migrations.RunPython.noop,
                )
            ],
            state_operations=[
                migrations.AlterModelOptions(
                    name="module",
                    options={"ordering": ["-id"], "verbose_name": "Module", "verbose_name_plural": "Module"},
                ),
                migrations.RemoveField(
                    model_name="module",
                    name="code",
                ),
                migrations.RemoveField(
                    model_name="module",
                    name="created_at",
                ),
                migrations.RemoveField(
                    model_name="module",
                    name="created_by",
                ),
                migrations.RemoveField(
                    model_name="module",
                    name="description",
                ),
                migrations.RemoveField(
                    model_name="module",
                    name="name",
                ),
                migrations.RemoveField(
                    model_name="module",
                    name="owner",
                ),
                migrations.RemoveField(
                    model_name="module",
                    name="status",
                ),
                migrations.RemoveField(
                    model_name="module",
                    name="updated_at",
                ),
                migrations.RemoveField(
                    model_name="module",
                    name="updated_by",
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_code",
                    field=models.CharField(db_column="MD_CODE", max_length=50, verbose_name="MD_CODE"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_create_date",
                    field=models.DateTimeField(blank=True, db_column="MD_CREATE_DATE", null=True, verbose_name="MD_CREATE_DATE"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_create_id",
                    field=models.IntegerField(blank=True, db_column="MD_CREATE_ID", null=True, verbose_name="MD_CREATE_ID"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_create_user",
                    field=models.CharField(blank=True, db_column="MD_CREATE_USER", max_length=50, null=True, verbose_name="MD_CREATE_USER"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_forbit_date",
                    field=models.DateTimeField(blank=True, db_column="MD_FORBIT_DATE", null=True, verbose_name="MD_FORBIT_DATE"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_forbit_id",
                    field=models.IntegerField(blank=True, db_column="MD_FORBIT_ID", null=True, verbose_name="MD_FORBIT_ID"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_forbit_user",
                    field=models.CharField(blank=True, db_column="MD_FORBIT_USER", max_length=50, null=True, verbose_name="MD_FORBIT_USER"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_ispoint",
                    field=models.IntegerField(db_column="MD_ISPOINT", verbose_name="MD_ISPOINT"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_modify_date",
                    field=models.DateTimeField(blank=True, db_column="MD_MODIFY_DATE", null=True, verbose_name="MD_MODIFY_DATE"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_modify_id",
                    field=models.IntegerField(blank=True, db_column="MD_MODIFY_ID", null=True, verbose_name="MD_MODIFY_ID"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_modify_user",
                    field=models.CharField(blank=True, db_column="MD_MODIFY_USER", max_length=50, null=True, verbose_name="MD_MODIFY_USER"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_name",
                    field=models.CharField(db_column="MD_NAME", max_length=200, verbose_name="MD_NAME"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_price",
                    field=models.DecimalField(db_column="MD_PRICE", decimal_places=2, max_digits=18, verbose_name="MD_PRICE"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_productcode",
                    field=models.CharField(blank=True, db_column="MD_PRODUCTCODE", max_length=50, null=True, verbose_name="MD_PRODUCTCODE"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_productid",
                    field=models.IntegerField(db_column="MD_PRODUCTID", verbose_name="MD_PRODUCTID"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_remark",
                    field=models.CharField(blank=True, db_column="MD_REMARK", max_length=100, null=True, verbose_name="MD_REMARK"),
                ),
                migrations.AddField(
                    model_name="module",
                    name="md_state",
                    field=models.IntegerField(blank=True, db_column="MD_STATE", null=True, verbose_name="MD_STATE"),
                ),
                migrations.AlterField(
                    model_name="module",
                    name="id",
                    field=models.AutoField(db_column="MD_ID", primary_key=True, serialize=False, verbose_name="MD_ID"),
                ),
                migrations.AlterModelTable(
                    name="module",
                    table="cljc_module",
                ),
            ],
        ),
    ]
