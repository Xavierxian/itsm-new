from django.urls import path

from logs.views import (
    AppLogListView,
    LoginLogListView,
    LogsDashboardView,
    OperationAuditLogListView,
    ResourceChangeLogListView,
    SecurityEventLogListView,
    TaskExecutionLogListView,
)

app_name = "logs"

urlpatterns = [
    path("", LogsDashboardView.as_view(), name="dashboard"),
    path("login/", LoginLogListView.as_view(), name="login-log-list"),
    path("audit/", OperationAuditLogListView.as_view(), name="audit-log-list"),
    path("app/", AppLogListView.as_view(), name="app-log-list"),
    path("tasks/", TaskExecutionLogListView.as_view(), name="task-log-list"),
    path("changes/", ResourceChangeLogListView.as_view(), name="resource-change-list"),
    path("security/", SecurityEventLogListView.as_view(), name="security-log-list"),
]
