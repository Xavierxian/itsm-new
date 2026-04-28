from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mappings", "0002_dns_records_all"),
    ]

    operations = [
        migrations.CreateModel(
            name="DNSRecord",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False, verbose_name="主键 ID")),
                ("platform", models.CharField(blank=True, max_length=20, null=True, verbose_name="DNS 平台")),
                ("domain_name", models.CharField(blank=True, max_length=255, null=True, verbose_name="主域名")),
                ("sub_domain", models.CharField(blank=True, max_length=255, null=True, verbose_name="子域名")),
                ("record_type", models.CharField(blank=True, max_length=20, null=True, verbose_name="记录类型")),
                ("record_line", models.CharField(blank=True, max_length=255, null=True, verbose_name="解析线路")),
                ("record_value", models.CharField(blank=True, max_length=255, null=True, verbose_name="记录值")),
                ("ttl", models.IntegerField(blank=True, null=True, verbose_name="TTL")),
                ("status", models.CharField(blank=True, max_length=20, null=True, verbose_name="状态")),
                ("weight", models.IntegerField(blank=True, null=True, verbose_name="权重")),
                ("mx_priority", models.IntegerField(blank=True, null=True, verbose_name="MX 优先级")),
                ("comment", models.CharField(blank=True, max_length=255, null=True, verbose_name="备注")),
                ("created_at", models.DateTimeField(blank=True, null=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(blank=True, null=True, verbose_name="更新时间")),
                ("raw_id", models.CharField(blank=True, max_length=64, null=True, verbose_name="源平台记录 ID")),
                ("last_sync_time", models.DateTimeField(blank=True, null=True, verbose_name="最后同步时间")),
            ],
            options={
                "verbose_name": "DNS 记录",
                "verbose_name_plural": "DNS 记录",
                "db_table": "dns_records_all",
                "ordering": ["-updated_at", "-id"],
                "managed": False,
            },
        ),
    ]
