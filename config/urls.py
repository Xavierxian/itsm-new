from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.conf import settings
from django.urls import include, path
from django.views.generic.base import RedirectView

handler403 = "core.error_views.permission_denied_view"

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=f"/{settings.STATIC_URL}images/title1.png", permanent=True)),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("assets/", include("assets.urls")),
    path("mappings/", include("mappings.urls")),
    path("bsecp/", include("bsecp.urls")),
    path("cloudops/", include("cloudops.urls")),
    path("monitoring/", include("monitoring.urls")),
    path("logs/", include("logs.urls")),
    path("api/v1/", include("core.api_urls")),
]

urlpatterns += staticfiles_urlpatterns()
