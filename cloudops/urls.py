from django.urls import path

from cloudops.views import (
    BastionCredentialPasswordAPIView,
    BastionCredentialsAPIView,
    BastionDeleteAPIView,
    BastionExportAPIView,
    BastionHostListView,
    BastionHostUserAuthAPIView,
    BastionHostsAPIView,
    BastionOnlineCountAPIView,
    BastionPingAPIView,
    BastionRestartAPIView,
    BastionSummaryAPIView,
    BastionUserInfoAPIView,
    SSHProxyRedirectView,
)

app_name = "cloudops"

urlpatterns = [
    path("bastions/", BastionHostListView.as_view(), name="bastion-list"),
    path("proxy/", SSHProxyRedirectView.as_view(), name="ssh-proxy"),
    path("api/bastions/summary/", BastionSummaryAPIView.as_view(), name="bastion-summary-api"),
    path("api/bastions/hosts/", BastionHostsAPIView.as_view(), name="bastion-hosts-api"),
    path("api/bastions/hosts/export/", BastionExportAPIView.as_view(), name="bastion-export-api"),
    path("api/bastions/hosts/<str:host_id>/credentials/", BastionCredentialsAPIView.as_view(), name="bastion-credentials-api"),
    path("api/bastions/hosts/<str:host_id>/restart/", BastionRestartAPIView.as_view(), name="bastion-restart-api"),
    path("api/bastions/hosts/<str:host_id>/delete/", BastionDeleteAPIView.as_view(), name="bastion-delete-api"),
    path("api/bastions/online-count/", BastionOnlineCountAPIView.as_view(), name="bastion-online-count-api"),
    path("api/bastions/users/<str:account>/", BastionUserInfoAPIView.as_view(), name="bastion-user-info-api"),
    path("api/bastions/credential-password/", BastionCredentialPasswordAPIView.as_view(), name="bastion-credential-password-api"),
    path("api/bastions/host-user-auth/", BastionHostUserAuthAPIView.as_view(), name="bastion-host-user-auth-api"),
    path("api/bastions/ping/", BastionPingAPIView.as_view(), name="bastion-ping-api"),
]
