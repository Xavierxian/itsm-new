from django.urls import path

from assets.views import (
    NamespaceCreateView,
    NamespaceListView,
    NamespaceUpdateView,
    PhysicalHostCreateView,
    PhysicalHostListView,
    PhysicalHostUpdateView,
    PurchaseDetailCreateView,
    PurchaseDetailUpdateView,
    QualificationHistoryApiView,
    QualificationManagementCreateView,
    QualificationManagementListView,
    QualificationManagementUpdateView,
    VirtualMachineCreateView,
    VirtualMachineListView,
    VirtualMachineUpdateView,
)

app_name = "assets"

urlpatterns = [
    path("virtual-machines/", VirtualMachineListView.as_view(), name="vm-list"),
    path("virtual-machines/create/", VirtualMachineCreateView.as_view(), name="vm-create"),
    path("virtual-machines/<int:pk>/edit/", VirtualMachineUpdateView.as_view(), name="vm-edit"),
    path("physical-hosts/", PhysicalHostListView.as_view(), name="host-list"),
    path("physical-hosts/create/", PhysicalHostCreateView.as_view(), name="host-create"),
    path("physical-hosts/<int:pk>/edit/", PhysicalHostUpdateView.as_view(), name="host-edit"),
    path("namespaces/", NamespaceListView.as_view(), name="namespace-list"),
    path("namespaces/create/", NamespaceCreateView.as_view(), name="namespace-create"),
    path("namespaces/<int:pk>/edit/", NamespaceUpdateView.as_view(), name="namespace-edit"),
    path("qualifications/", QualificationManagementListView.as_view(), name="qualification-list"),
    path("qualifications/<int:pk>/history/", QualificationHistoryApiView.as_view(), name="qualification-history"),
    path("qualifications/<int:qualification_pk>/history-records/create/", PurchaseDetailCreateView.as_view(), name="purchase-detail-create"),
    path("history-records/<int:pk>/edit/", PurchaseDetailUpdateView.as_view(), name="purchase-detail-edit"),
    path("qualifications/create/", QualificationManagementCreateView.as_view(), name="qualification-create"),
    path("qualifications/<int:pk>/edit/", QualificationManagementUpdateView.as_view(), name="qualification-edit"),
]
