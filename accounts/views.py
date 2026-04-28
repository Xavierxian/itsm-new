from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import FormView

from accounts.forms import LoginForm, ProfilePasswordChangeForm, RoleForm, UserForm
from accounts.models import Role, SessionRecord
from accounts.security import is_login_rate_limited, register_login_failure, reset_login_failures
from core.views import ManagedCreateView, ManagedUpdateView, SearchableListView
from logs.models import SecurityEventLog
from logs.utils import get_client_ip, log_login_attempt, log_operation, log_security_event

User = get_user_model()


class LoginView(FormView):
    template_name = "auth/login.html"
    form_class = LoginForm
    success_url = reverse_lazy("core:dashboard")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["failure_limit"] = int(getattr(settings, "LOGIN_FAILURE_LIMIT", 5))
        context["lock_minutes"] = int(getattr(settings, "LOGIN_LOCK_MINUTES", 15))
        context["next_url"] = self.request.GET.get("next", "")
        return context

    def _generic_failure(self, form, *, status=200, message=None):
        messages.error(self.request, message or "用户名或密码错误。")
        return self.render_to_response(self.get_context_data(form=form), status=status)

    def _lockout_message(self, locked_until=None):
        lock_minutes = int(getattr(settings, "LOGIN_LOCK_MINUTES", 15))
        if locked_until:
            local_until = timezone.localtime(locked_until).strftime("%H:%M")
            return f"账号已锁定，请于 {local_until} 后重试。"
        return f"账号已锁定，请 {lock_minutes} 分钟后重试。"

    def _remaining_attempts_message(self, attempts_used):
        failure_limit = int(getattr(settings, "LOGIN_FAILURE_LIMIT", 5))
        lock_minutes = int(getattr(settings, "LOGIN_LOCK_MINUTES", 15))
        remaining = max(0, failure_limit - int(attempts_used or 0))
        if remaining == 0:
            return f"账号已锁定，连续失败 {failure_limit} 次，需等待 {lock_minutes} 分钟后重试。"
        return (
            f"用户名或密码错误。连续失败 {failure_limit} 次将锁定 {lock_minutes} 分钟，"
            f"剩余 {remaining} 次。"
        )

    def _record_lockout_event(self, user, username, ip_address):
        log_security_event(
            event_type=SecurityEventLog.EventTypeChoices.LOCKOUT,
            severity=SecurityEventLog.SeverityChoices.HIGH,
            description=f"账号登录失败次数超过阈值并触发锁定(IP: {ip_address})",
            request=self.request,
            user=user,
            username=username,
        )

    def _handle_failed_login(self, form, username, user=None, reason="用户名或密码错误"):
        ip_address = get_client_ip(self.request)
        counters = register_login_failure(username=username, ip_address=ip_address)

        user_locked = False
        if user:
            user.register_login_failure(lock_minutes=settings.LOGIN_LOCK_MINUTES)
            user.save(update_fields=["failed_login_attempts", "locked_until", "status"])
            user_locked = user.is_locked

        log_login_attempt(
            request=self.request,
            success=False,
            user=user,
            username=username,
            failure_reason=reason,
        )

        if user_locked:
            self._record_lockout_event(user, username, ip_address)
            return self._generic_failure(form, status=429, message=self._lockout_message(user.locked_until))

        if counters["ip_user_count"] >= settings.LOGIN_RATE_LIMIT_PER_IP_USER:
            log_security_event(
                event_type=SecurityEventLog.EventTypeChoices.ABNORMAL_LOGIN,
                severity=SecurityEventLog.SeverityChoices.MEDIUM,
                description=f"单IP+账号登录尝试超过限制(IP: {ip_address})",
                request=self.request,
                user=user,
                username=username,
            )

        if user:
            return self._generic_failure(form, message=self._remaining_attempts_message(user.failed_login_attempts))
        return self._generic_failure(form)

    def form_valid(self, form):
        username = form.cleaned_data["username"]
        password = form.cleaned_data["password"]
        ip_address = get_client_ip(self.request)
        user = User.objects.filter(username=username).first()

        if is_login_rate_limited(username=username, ip_address=ip_address):
            log_login_attempt(
                request=self.request,
                success=False,
                user=user,
                username=username,
                failure_reason="登录请求过于频繁",
            )
            log_security_event(
                event_type=SecurityEventLog.EventTypeChoices.ABNORMAL_LOGIN,
                severity=SecurityEventLog.SeverityChoices.HIGH,
                description=f"触发登录限流策略(IP: {ip_address})",
                request=self.request,
                user=user,
                username=username,
            )
            return self._generic_failure(form, status=429, message="登录过于频繁，请稍后再试。")

        if user and user.is_locked:
            log_login_attempt(
                request=self.request,
                success=False,
                user=user,
                username=username,
                failure_reason="账号处于锁定状态",
            )
            self._record_lockout_event(user, username, ip_address)
            return self._generic_failure(form, status=429, message=self._lockout_message(user.locked_until))

        authenticated_user = authenticate(self.request, username=username, password=password)
        if not authenticated_user:
            return self._handle_failed_login(form, username=username, user=user)

        if (
            authenticated_user.status == User.StatusChoices.DISABLED
            or not authenticated_user.is_active
            or not authenticated_user.is_staff
        ):
            return self._handle_failed_login(
                form,
                username=username,
                user=authenticated_user,
                reason="账号状态受限，拒绝登录",
            )

        login(self.request, authenticated_user)
        reset_login_failures(username=username, ip_address=ip_address)
        authenticated_user.reset_login_failures()
        authenticated_user.last_login = timezone.now()
        authenticated_user.save(update_fields=["failed_login_attempts", "locked_until", "status", "last_login"])
        session = SessionRecord.objects.create(
            user=authenticated_user,
            session_key=self.request.session.session_key or "",
            ip_address=ip_address,
            user_agent=self.request.META.get("HTTP_USER_AGENT", "")[:255],
        )
        self.request.session["session_record_id"] = session.pk
        log_login_attempt(request=self.request, success=True, user=authenticated_user, username=username)
        log_operation(
            user=authenticated_user,
            module="accounts",
            action="login",
            request=self.request,
            result="success",
        )
        messages.success(self.request, "欢迎回来。")
        return super().form_valid(form)

class LogoutView(View):
    def post(self, request, *args, **kwargs):
        session_id = request.session.get("session_record_id")
        if session_id:
            SessionRecord.objects.filter(pk=session_id).update(
                logout_at=timezone.now(),
                status=SessionRecord.SessionStatusChoices.LOGGED_OUT,
            )
        if request.user.is_authenticated:
            log_operation(user=request.user, module="accounts", action="logout", request=request, result="success")
        logout(request)
        messages.info(request, "已安全退出。")
        return redirect("accounts:login")


class PasswordChangeView(LoginRequiredMixin, FormView):
    template_name = "auth/password_change.html"
    form_class = ProfilePasswordChangeForm
    success_url = reverse_lazy("core:dashboard")
    page_title = "修改密码"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url and next_url != self.request.path:
            return next_url
        return str(self.success_url)

    def form_valid(self, form):
        user = form.save()
        user.password_changed_at = timezone.now()
        user.save(update_fields=["password_changed_at"])
        update_session_auth_hash(self.request, user)
        log_operation(
            user=user,
            module="accounts",
            action="change_password",
            request=self.request,
            result="success",
        )
        messages.success(self.request, "密码更新成功。")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["submit_label"] = "更新密码"
        context["next_url"] = self.request.GET.get("next", "")
        context["password_rules_html"] = self.form_class(self.request.user).fields["new_password1"].help_text
        return context


class UserListView(SearchableListView):
    model = User
    permission_required = "accounts.view_user"
    page_title = "用户管理"
    page_description = "管理平台登录账号、角色和状态。"
    search_fields = ["username", "full_name", "email", "phone_number"]
    columns = [("账号", "username"), ("姓名", "full_name"), ("邮箱", "email"), ("手机号", "phone_number"), ("状态", "get_status_display")]
    create_url_name = "accounts:user-create"
    edit_url_name = "accounts:user-edit"


class UserCreateView(ManagedCreateView):
    model = User
    form_class = UserForm
    permission_required = "accounts.add_user"
    page_title = "新增用户"
    success_url = reverse_lazy("accounts:user-list")


class UserUpdateView(ManagedUpdateView):
    model = User
    form_class = UserForm
    permission_required = "accounts.change_user"
    page_title = "编辑用户"
    success_url = reverse_lazy("accounts:user-list")
    allow_delete = True
    delete_permission_required = "accounts.delete_user"
    delete_label = "删除用户"
    delete_confirm_text = "确认删除该用户吗？删除后不可恢复。"
    delete_success_message = "用户删除成功。"

    def can_delete_object(self, obj):
        if self.request.user.pk == obj.pk:
            return False, "不允许删除当前登录账号。"
        return True, ""


class RoleListView(SearchableListView):
    model = Role
    permission_required = "accounts.view_role"
    page_title = "角色管理"
    page_description = "为企业内部角色分配权限和数据范围。"
    search_fields = ["name", "description"]
    columns = [("角色名称", "name"), ("数据范围", "get_data_scope_display"), ("说明", "description")]
    create_url_name = "accounts:role-create"
    edit_url_name = "accounts:role-edit"


class RoleFormContextMixin:
    template_name = "accounts/role_form.html"

    def _build_permission_groups(self, form):
        selected_values = {str(value) for value in (form["permissions"].value() or [])}
        groups = {}

        for permission in form.fields["permissions"].queryset:
            app_label = (permission.content_type.app_label or "other").strip()
            group_name = app_label.replace("_", " ").title() if app_label.isascii() else app_label
            resource_name = (permission.content_type.name or permission.content_type.model or "General").strip()
            action_name = (permission.name or permission.codename or "").strip()

            group = groups.setdefault(
                app_label,
                {
                    "key": app_label,
                    "name": group_name,
                    "items": [],
                    "selected_count": 0,
                    "total_count": 0,
                },
            )

            item = {
                "id": str(permission.pk),
                "resource": resource_name,
                "action": action_name,
                "codename": permission.codename,
                "search_text": f"{group_name} {resource_name} {action_name} {permission.codename}".lower(),
                "selected": str(permission.pk) in selected_values,
            }
            group["items"].append(item)
            group["total_count"] += 1
            if item["selected"]:
                group["selected_count"] += 1

        return list(groups.values())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        if form is not None:
            permission_groups = self._build_permission_groups(form)
            context["permission_groups"] = permission_groups
            context["permission_selected_count"] = sum(group["selected_count"] for group in permission_groups)
            context["permission_total_count"] = sum(group["total_count"] for group in permission_groups)
        return context


class RoleCreateView(RoleFormContextMixin, ManagedCreateView):
    template_name = "accounts/role_form.html"
    model = Role
    form_class = RoleForm
    permission_required = "accounts.add_role"
    page_title = "新增角色"
    success_url = reverse_lazy("accounts:role-list")


class RoleUpdateView(RoleFormContextMixin, ManagedUpdateView):
    template_name = "accounts/role_form.html"
    model = Role
    form_class = RoleForm
    permission_required = "accounts.change_role"
    page_title = "编辑角色"
    success_url = reverse_lazy("accounts:role-list")

