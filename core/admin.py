from django.contrib import admin

from core.models import Notification, SystemSetting


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "level", "is_published", "created_at")
    list_filter = ("level", "is_published")
    search_fields = ("title", "content")


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "is_sensitive", "updated_at")
    list_filter = ("is_sensitive",)
    search_fields = ("key", "description")

