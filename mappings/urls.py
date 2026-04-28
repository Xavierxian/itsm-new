from django.urls import path

from mappings.views import (
    DomainMappingListView,
    PortMappingCreateView,
    PortMappingListView,
    PortMappingUpdateView,
)

app_name = "mappings"

urlpatterns = [
    path("ports/", PortMappingListView.as_view(), name="port-list"),
    path("ports/create/", PortMappingCreateView.as_view(), name="port-create"),
    path("ports/<int:pk>/edit/", PortMappingUpdateView.as_view(), name="port-edit"),
    path("domains/", DomainMappingListView.as_view(), name="domain-list"),
]
