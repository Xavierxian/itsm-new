from django.urls import path

from core.api_views import CurrentUserAPIView, HealthAPIView

app_name = "core_api"

urlpatterns = [
    path("health/", HealthAPIView.as_view(), name="health"),
    path("me/", CurrentUserAPIView.as_view(), name="me"),
]

