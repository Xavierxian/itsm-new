from django.urls import path

from accounts.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    RoleCreateView,
    RoleListView,
    RoleUpdateView,
    UserCreateView,
    UserListView,
    UserUpdateView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("password/", PasswordChangeView.as_view(), name="password-change"),
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/create/", UserCreateView.as_view(), name="user-create"),
    path("users/<int:pk>/edit/", UserUpdateView.as_view(), name="user-edit"),
    path("roles/", RoleListView.as_view(), name="role-list"),
    path("roles/create/", RoleCreateView.as_view(), name="role-create"),
    path("roles/<int:pk>/edit/", RoleUpdateView.as_view(), name="role-edit"),
]
