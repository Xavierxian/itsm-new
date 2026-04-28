from django.db import models

from core.models import ManagedModel


class BastionHost(ManagedModel):
    name = models.CharField(max_length=120, unique=True, verbose_name="堡垒机名称")
    endpoint = models.CharField(max_length=160, verbose_name="访问地址")
    username_hint = models.CharField(max_length=80, blank=True, verbose_name="登录提示")
    description = models.CharField(max_length=255, blank=True, verbose_name="说明")

    class Meta:
        ordering = ["name"]
        verbose_name = "堡垒机"
        verbose_name_plural = "堡垒机"

    def __str__(self):
        return self.name
