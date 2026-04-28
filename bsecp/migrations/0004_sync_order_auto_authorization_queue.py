# Generated manually to align DB schema with OrderAutoAuthorizationQueue
from django.db import migrations


def sync_order_auto_authorization_queue(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if vendor == "mysql":
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cursor.execute("DROP TABLE IF EXISTS `OrderAutoAuthorizationQueue`;")
            cursor.execute(
                """
                CREATE TABLE `OrderAutoAuthorizationQueue` (
                  `FId` int NOT NULL AUTO_INCREMENT COMMENT '主键ID，自增',
                  `OD_SERIAL_NUMBER` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '订单流水号',
                  `OD_CONTRACT_NUMBER` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '合同编号',
                  `OD_BMPID` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '业务主键ID（业务系统标识）',
                  `AutoAuthFlag` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '自动授权标识（如：Y=需要自动授权，N=不需要）',
                  `Remark` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '备注信息',
                  `CreateTime` datetime NULL DEFAULT NULL COMMENT '创建时间（入队时间）',
                  `AutoAuthHandleTime` datetime NULL DEFAULT NULL COMMENT '自动授权处理时间',
                  `AutoAuthHandleResult` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '自动授权处理结果（如：SUCCESS/FAIL）',
                  `AutoAuthHandleResultDesc` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL COMMENT '自动授权处理结果描述（失败原因等）',
                  PRIMARY KEY (`FId`) USING BTREE
                ) ENGINE=InnoDB
                AUTO_INCREMENT=4540
                DEFAULT CHARSET=utf8mb4
                COLLATE=utf8mb4_general_ci
                ROW_FORMAT=Dynamic
                COMMENT='订单自动授权处理队列表';
                """
            )
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        elif vendor == "sqlite":
            cursor.execute('DROP TABLE IF EXISTS "OrderAutoAuthorizationQueue";')
            cursor.execute(
                """
                CREATE TABLE "OrderAutoAuthorizationQueue" (
                  "FId" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                  "OD_SERIAL_NUMBER" varchar(255) NULL,
                  "OD_CONTRACT_NUMBER" varchar(255) NULL,
                  "OD_BMPID" varchar(255) NULL,
                  "AutoAuthFlag" varchar(255) NULL,
                  "Remark" text NULL,
                  "CreateTime" datetime NULL,
                  "AutoAuthHandleTime" datetime NULL,
                  "AutoAuthHandleResult" varchar(255) NULL,
                  "AutoAuthHandleResultDesc" text NULL
                );
                """
            )


class Migration(migrations.Migration):
    dependencies = [
        ("bsecp", "0003_alter_authorizationrecord_table"),
    ]

    operations = [
        migrations.RunPython(sync_order_auto_authorization_queue, migrations.RunPython.noop),
    ]

