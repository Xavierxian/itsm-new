from django.db import migrations


CREATE_DNS_RECORDS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `dns_records_all` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `platform` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'DNS平台（如阿里云、腾讯云、华为云等）',
  `domain_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '主域名（如 example.com）',
  `sub_domain` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '子域名（如 www、api，为空表示根域名）',
  `record_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '记录类型（A、AAAA、CNAME、MX、TXT等）',
  `record_line` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '解析线路（默认、联通、电信、海外等）',
  `record_value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '记录值（IP地址或指向的域名）',
  `ttl` int DEFAULT NULL COMMENT 'TTL（缓存时间，单位：秒）',
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '状态（ENABLE=启用，DISABLE=暂停）',
  `weight` int DEFAULT NULL COMMENT '权重（用于负载均衡）',
  `mx_priority` int DEFAULT NULL COMMENT 'MX优先级（仅MX记录有效）',
  `comment` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '备注信息',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  `raw_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '源平台记录ID（云厂商返回）',
  `last_sync_time` datetime DEFAULT NULL COMMENT '最后同步时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uniq_idx` (`platform`, `raw_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("mappings", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_DNS_RECORDS_TABLE_SQL,
            reverse_sql="DROP TABLE IF EXISTS `dns_records_all`;",
        ),
    ]
