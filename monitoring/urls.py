from django.urls import path

from monitoring.views import (
    HostResourceAlertNotifyAPIView,
    HostResourceAlertsAPIView,
    HostResourceDashboardView,
    HostResourceDataAPIView,
    HostResourceTargetsAPIView,
    HostResourceTrendAPIView,
    K8SAnalysisAPIView,
    K8SNamespaceAnalysisStreamAPIView,
    K8SNodeAnalysisStreamAPIView,
    K8SNodeTrendAPIView,
    K8SNamespaceTrendAPIView,
    K8SNamespacesAPIView,
    K8SNodesAPIView,
    K8SResourceDashboardView,
    K8SSummaryAPIView,
    MonitoringTargetListView,
    ScheduledTaskRecordListView,
)

app_name = "monitoring"

urlpatterns = [
    path("host-resources/", HostResourceDashboardView.as_view(), name="host-resource-dashboard"),
    path("api/host-resources/data/", HostResourceDataAPIView.as_view(), name="host-resource-data-api"),
    path("api/host-resources/alerts/", HostResourceAlertsAPIView.as_view(), name="host-resource-alerts-api"),
    path("api/host-resources/alerts/notify/", HostResourceAlertNotifyAPIView.as_view(), name="host-resource-alert-notify-api"),
    path("api/host-resources/targets/", HostResourceTargetsAPIView.as_view(), name="host-resource-targets-api"),
    path("api/host-resources/trends/<path:instance>/", HostResourceTrendAPIView.as_view(), name="host-resource-trend-api"),
    path("k8s-resources/", K8SResourceDashboardView.as_view(), name="k8s-resource-dashboard"),
    path("api/k8s/summary/", K8SSummaryAPIView.as_view(), name="k8s-summary-api"),
    path("api/k8s/namespaces/", K8SNamespacesAPIView.as_view(), name="k8s-namespaces-api"),
    path("api/k8s/nodes/", K8SNodesAPIView.as_view(), name="k8s-nodes-api"),
    path("api/k8s/trends/<path:namespace>/", K8SNamespaceTrendAPIView.as_view(), name="k8s-namespace-trend-api"),
    path("api/k8s/node-trends/<path:node_ip>/", K8SNodeTrendAPIView.as_view(), name="k8s-node-trend-api"),
    path("api/k8s/analysis/", K8SAnalysisAPIView.as_view(), name="k8s-analysis-api"),
    path("api/k8s/analysis/stream/<path:namespace>/", K8SNamespaceAnalysisStreamAPIView.as_view(), name="k8s-analysis-stream-api"),
    path("api/k8s/node-analysis/stream/<path:node_ip>/", K8SNodeAnalysisStreamAPIView.as_view(), name="k8s-node-analysis-stream-api"),
    path("targets/", MonitoringTargetListView.as_view(), name="target-list"),
    path("tasks/", ScheduledTaskRecordListView.as_view(), name="task-list"),
]
