from django.contrib import admin

from monitoring.models import MonitoringTarget, ScheduledTaskRecord

admin.site.register(MonitoringTarget)
admin.site.register(ScheduledTaskRecord)

