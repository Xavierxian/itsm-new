from django.contrib import admin

from logs.models import AppLogIndex, LoginLog, OperationAuditLog, ResourceChangeLog, SecurityEventLog, TaskExecutionLog

admin.site.register(LoginLog)
admin.site.register(OperationAuditLog)
admin.site.register(AppLogIndex)
admin.site.register(TaskExecutionLog)
admin.site.register(ResourceChangeLog)
admin.site.register(SecurityEventLog)

