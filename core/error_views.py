from django.shortcuts import render
from django.urls import reverse


def permission_denied_view(request, exception=None):
    dashboard_url = reverse("core:dashboard") if request.user.is_authenticated else reverse("accounts:login")
    back_url = request.META.get("HTTP_REFERER") or dashboard_url
    context = {
        "dashboard_url": dashboard_url,
        "back_url": back_url,
        "dashboard_label": "返回仪表盘" if request.user.is_authenticated else "前往登录",
        "requested_path": request.get_full_path(),
        "trace_id": getattr(request, "trace_id", ""),
        "exception_message": str(exception) if exception else "",
    }
    return render(request, "403.html", context, status=403)
