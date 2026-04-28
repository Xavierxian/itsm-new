from django.urls import path

from bsecp.views import (
    AuthorizationDetailListView,
    AuthorizationDetailSuggestView,
    AuthorizationRecordListView,
    ModuleCreateView,
    ModuleListView,
    ModuleUpdateView,
)

app_name = "bsecp"

urlpatterns = [
    path("modules/", ModuleListView.as_view(), name="module-list"),
    path("modules/create/", ModuleCreateView.as_view(), name="module-create"),
    path("modules/<int:pk>/edit/", ModuleUpdateView.as_view(), name="module-edit"),
    path("authorizations/", AuthorizationRecordListView.as_view(), name="authorization-list"),
    path("authorization-details/", AuthorizationDetailListView.as_view(), name="authorization-detail"),
    path("authorization-details/suggest/", AuthorizationDetailSuggestView.as_view(), name="authorization-detail-suggest"),
]
