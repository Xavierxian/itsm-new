from django.urls import path

from core.views import DashboardView, HomeRedirectView

app_name = "core"

urlpatterns = [
    path("", HomeRedirectView.as_view(), name="home"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]

