from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logs", "0003_add_performance_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="securityeventlog",
            name="status",
            field=models.CharField(
                choices=[("open", "待处理"), ("in_progress", "处理中"), ("resolved", "已关闭")],
                default="resolved",
                max_length=20,
                verbose_name="处理状态",
            ),
        ),
    ]
