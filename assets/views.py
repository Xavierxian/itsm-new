import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View

from assets.forms import (
    NamespaceForm,
    PhysicalHostForm,
    PurchaseDetailFormSet,
    PurchaseDetailManageForm,
    QualificationManagementForm,
    VirtualMachineForm,
)
from assets.models import Namespace, PhysicalHost, PurchaseDetail, QualificationManagement, VirtualMachine
from core.views import ManagedCreateView, ManagedUpdateView, SearchableListView
from logs.utils import log_operation


def _normalize_cost_amount_for_parent(value):
    if value is None:
        return None
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        text_value = str(value).strip()
        return text_value or None

    text_value = format(decimal_value, "f")
    if "." in text_value:
        text_value = text_value.rstrip("0").rstrip(".")
    return text_value or "0"


def sync_qualification_snapshot_from_latest_detail(qualification):
    latest_detail = (
        PurchaseDetail.objects.filter(parent_id=qualification.pk)
        .order_by("-create_time", "-id")
        .first()
    )
    if not latest_detail:
        return

    qualification.cost = _normalize_cost_amount_for_parent(latest_detail.cost_amount)
    qualification.expire_date = latest_detail.expire_date.date() if latest_detail.expire_date else None
    qualification.last_update_time = timezone.now()
    qualification.save(update_fields=["cost", "expire_date", "last_update_time"])


class VirtualMachineListView(SearchableListView):
    template_name = "assets/vm_list.html"
    model = VirtualMachine
    permission_required = "assets.view_virtualmachine"
    page_title = "虚拟机资产"
    page_description = "以卡片方式展示 assets 表中的虚拟机资产信息。"
    search_fields = ["host_ip", "vm_ip", "os_name", "os_version", "login_name", "applicant", "department", "purpose", "environment", "in_use"]
    columns = [
        ("主机IP", "host_ip"),
        ("虚拟机IP", "vm_ip"),
        ("系统", "os_summary"),
        ("登录", "login_name"),
        ("端口", "remote_port"),
        ("规格", "spec_summary"),
        ("归属", "owner_summary"),
        ("用途", "purpose"),
        ("环境", "environment"),
        ("周期", "period_summary"),
        ("状态", "in_use_label"),
    ]
    create_url_name = "assets:vm-create"
    edit_url_name = "assets:vm-edit"
    panel_css_class = "list-panel-v4-assetsvm"
    color_result_field = "in_use_label"
    result_success_values = ("在用",)
    result_failure_values = ("停用",)

    def _base_queryset(self):
        return super().get_queryset()

    def get_queryset(self):
        queryset = self._base_queryset()
        os_filter = self.request.GET.get("os", "").strip()
        if os_filter == "__empty__":
            queryset = queryset.filter(Q(os_name__isnull=True) | Q(os_name__exact=""))
        elif os_filter:
            queryset = queryset.filter(os_name__iexact=os_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = self._base_queryset()
        total_count = base_queryset.count()
        active_os_filter = (self.request.GET.get("os", "").strip()).casefold()

        os_counter = {}
        os_label_map = {}
        preferred_labels = {
            "windows": "Windows",
            "centos": "CentOS",
            "ubuntu": "Ubuntu",
            "xenserver": "XenServer",
        }
        for os_name in base_queryset.values_list("os_name", flat=True):
            raw_label = " ".join(((os_name or "").strip()).split()) or "未填写"
            normalized_key = raw_label.casefold()
            os_counter[normalized_key] = os_counter.get(normalized_key, 0) + 1
            if normalized_key not in os_label_map:
                os_label_map[normalized_key] = preferred_labels.get(normalized_key, raw_label)

        sorted_os_stats = sorted(
            ((key, os_label_map[key], count) for key, count in os_counter.items()),
            key=lambda item: (-item[2], item[1].casefold()),
        )
        accent_cycle = ["is-primary", "is-success", "is-warning", "is-info"]
        os_icon_map = {
            "windows": "os-windows",
            "centos": "os-penguin",
            "ubuntu": "os-ubuntu",
            "xenserver": "network",
        }
        context["summary_cards"] = [
            {
                "value": total_count,
                "label": "Total",
                "accent_class": "is-primary",
                "icon": "stack",
                "filter_url": self.build_list_url(os=""),
                "is_active": not active_os_filter,
            },
        ] + [
            {
                "value": count,
                "label": os_label,
                "accent_class": accent_cycle[(index + 1) % len(accent_cycle)],
                "icon": os_icon_map.get(os_key, "network"),
                "filter_url": self.build_list_url(os="__empty__" if os_label == "未填写" else os_label),
                "is_active": (active_os_filter == "__empty__" if os_label == "未填写" else active_os_filter == os_label.casefold()),
            }
            for index, (os_key, os_label, count) in enumerate(sorted_os_stats)
        ]
        return context


class VirtualMachineCreateView(ManagedCreateView):
    model = VirtualMachine
    form_class = VirtualMachineForm
    permission_required = "assets.add_virtualmachine"
    page_title = "新增虚拟机资产"
    success_url = reverse_lazy("assets:vm-list")


class VirtualMachineUpdateView(ManagedUpdateView):
    model = VirtualMachine
    form_class = VirtualMachineForm
    permission_required = "assets.change_virtualmachine"
    page_title = "编辑虚拟机资产"
    success_url = reverse_lazy("assets:vm-list")

    def post(self, request, *args, **kwargs):
        if request.POST.get("_action") == "delete":
            return self._delete_asset(request)
        return super().post(request, *args, **kwargs)

    def _delete_asset(self, request):
        if not request.user.has_perm("assets.delete_virtualmachine"):
            raise PermissionDenied

        target = self.get_object()
        try:
            target.delete()
        except Exception:
            log_operation(
                user=request.user,
                module=self.model._meta.app_label,
                action="delete",
                target=target,
                request=request,
                result="failed",
            )
            raise

        log_operation(
            user=request.user,
            module=self.model._meta.app_label,
            action="delete",
            target=target,
            request=request,
            result="success",
        )
        messages.success(request, "虚拟机资产已删除。")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_delete_button"] = self.request.user.has_perm("assets.delete_virtualmachine")
        context["delete_label"] = "删除"
        context["delete_confirm_text"] = "确认删除这条虚拟机资产记录吗？"
        return context


class PhysicalHostListView(SearchableListView):
    template_name = "assets/host_list.html"
    model = PhysicalHost
    permission_required = "assets.view_physicalhost"
    page_title = "物理机"
    page_description = "展示 xenserver 表中的物理机资产信息。"
    search_fields = [
        "server_ip",
        "model_name",
        "purchase_channel",
        "department",
        "purpose",
    ]
    columns = [
        ("服务器IP", "server_ip"),
        ("型号", "model_name"),
        ("购买途径", "purchase_channel"),
        ("购买日期", "purchase_date"),
        ("端口", "port"),
        ("内存", "memory"),
        ("磁盘", "disk"),
        ("剩余可开", "remaining_capacity"),
        ("部门", "department"),
        ("用途", "purpose"),
    ]
    create_url_name = "assets:host-create"
    edit_url_name = "assets:host-edit"

    def _base_queryset(self):
        return super().get_queryset()

    def get_queryset(self):
        queryset = self._base_queryset()
        channel_filter = self.request.GET.get("channel", "").strip()
        if channel_filter == "__empty__":
            queryset = queryset.filter(Q(purchase_channel__isnull=True) | Q(purchase_channel__exact=""))
        elif channel_filter:
            queryset = queryset.filter(purchase_channel__iexact=channel_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_channel_filter = (self.request.GET.get("channel", "").strip()).casefold()
        base_queryset = self._base_queryset()
        total_count = base_queryset.count()
        channel_rows = (
            base_queryset.values("purchase_channel")
            .annotate(total=Count("id"))
            .order_by("-total", "purchase_channel")
        )
        accent_cycle = ["is-primary", "is-success", "is-warning", "is-info"]
        icon_cycle = ["network", "success", "warning", "stack"]
        context["summary_cards"] = [
            {
                "value": total_count,
                "label": "Total",
                "accent_class": "is-primary",
                "icon": "network",
                "filter_url": self.build_list_url(channel=""),
                "is_active": not active_channel_filter,
            }
        ] + [
            {
                "value": row["total"],
                "label": (row["purchase_channel"] or "未填写"),
                "accent_class": accent_cycle[(index + 1) % len(accent_cycle)],
                "icon": icon_cycle[(index + 1) % len(icon_cycle)],
                "filter_url": self.build_list_url(channel="__empty__" if not row["purchase_channel"] else row["purchase_channel"]),
                "is_active": (
                    active_channel_filter == "__empty__"
                    if not row["purchase_channel"]
                    else active_channel_filter == row["purchase_channel"].casefold()
                ),
            }
            for index, row in enumerate(channel_rows)
        ]
        return context


class PhysicalHostCreateView(ManagedCreateView):
    model = PhysicalHost
    form_class = PhysicalHostForm
    permission_required = "assets.add_physicalhost"
    page_title = "新增物理机"
    success_url = reverse_lazy("assets:host-list")


class PhysicalHostUpdateView(ManagedUpdateView):
    model = PhysicalHost
    form_class = PhysicalHostForm
    permission_required = "assets.change_physicalhost"
    page_title = "编辑物理机"
    success_url = reverse_lazy("assets:host-list")

    def post(self, request, *args, **kwargs):
        if request.POST.get("_action") == "delete":
            return self._delete_host(request)
        return super().post(request, *args, **kwargs)

    def _delete_host(self, request):
        if not request.user.has_perm("assets.delete_physicalhost"):
            raise PermissionDenied

        target = self.get_object()
        try:
            target.delete()
        except Exception:
            log_operation(
                user=request.user,
                module=self.model._meta.app_label,
                action="delete",
                target=target,
                request=request,
                result="failed",
            )
            raise

        log_operation(
            user=request.user,
            module=self.model._meta.app_label,
            action="delete",
            target=target,
            request=request,
            result="success",
        )
        messages.success(request, "物理机记录已删除。")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_delete_button"] = self.request.user.has_perm("assets.delete_physicalhost")
        context["delete_label"] = "删除"
        context["delete_confirm_text"] = "确认删除这条物理机记录吗？"
        return context


class NamespaceListView(SearchableListView):
    model = Namespace
    permission_required = "assets.view_namespace"
    page_title = "NameSpace"
    page_description = "展示 bseip 表中的命名空间信息。"
    search_fields = [
        "namespace_name",
        "space_owner",
        "request_department",
        "space_contact",
        "service_engineer",
        "purpose",
        "disabled",
    ]
    columns = [
        ("命名空间", "namespace_name"),
        ("空间归属", "space_owner"),
        ("申请部门", "request_department"),
        ("空间对接人", "space_contact"),
        ("服务工程师", "service_engineer"),
        ("开通日期", "open_date"),
        ("到期日期", "expiry_date"),
        ("用途", "purpose"),
        ("是否停用", "disabled_label"),
    ]
    create_url_name = "assets:namespace-create"
    edit_url_name = "assets:namespace-edit"
    panel_css_class = "list-panel-v4-namespace"
    color_result_field = "disabled_label"
    result_success_values = ("启用",)
    result_failure_values = ("停用",)


class NamespaceCreateView(ManagedCreateView):
    model = Namespace
    form_class = NamespaceForm
    permission_required = "assets.add_namespace"
    page_title = "新增 NameSpace"
    success_url = reverse_lazy("assets:namespace-list")


class NamespaceUpdateView(ManagedUpdateView):
    model = Namespace
    form_class = NamespaceForm
    permission_required = "assets.change_namespace"
    page_title = "编辑 NameSpace"
    success_url = reverse_lazy("assets:namespace-list")

    def post(self, request, *args, **kwargs):
        if request.POST.get("_action") == "delete":
            return self._delete_namespace(request)
        return super().post(request, *args, **kwargs)

    def _delete_namespace(self, request):
        if not request.user.has_perm("assets.delete_namespace"):
            raise PermissionDenied

        target = self.get_object()
        try:
            target.delete()
        except Exception:
            log_operation(
                user=request.user,
                module=self.model._meta.app_label,
                action="delete",
                target=target,
                request=request,
                result="failed",
            )
            raise

        log_operation(
            user=request.user,
            module=self.model._meta.app_label,
            action="delete",
            target=target,
            request=request,
            result="success",
        )
        messages.success(request, "NameSpace 记录已删除。")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_delete_button"] = self.request.user.has_perm("assets.delete_namespace")
        context["delete_label"] = "删除"
        context["delete_confirm_text"] = "确认删除这条 NameSpace 记录吗？"
        return context


class QualificationManagementListView(SearchableListView):
    template_name = "assets/qualification_list.html"
    model = QualificationManagement
    permission_required = "assets.view_qualificationmanagement"
    page_title = "资质管理"
    page_description = "展示资质信息以及关联采购/修改记录数量。"
    search_fields = [
        "qualification_category",
        "belong_entity",
        "belong_department",
        "qualification_name",
        "manager",
        "usage",
        "cost",
        "account",
        "status",
        "remark",
        "supplier_name",
    ]
    columns = [
        ("资质类别", "qualification_category"),
        ("资质名称", "qualification_name"),
        ("归属主体", "belong_entity"),
        ("归属部门", "belong_department"),
        ("管理员", "manager"),
        ("状态", "status_label"),
        ("到期日", "expire_date"),
        ("费用", "cost"),
        ("供应商", "supplier_name"),
        ("修改记录数", "purchase_detail_count"),
        ("最新修改日期", "last_update_time"),
    ]
    create_url_name = "assets:qualification-create"
    edit_url_name = "assets:qualification-edit"
    show_actions = True
    panel_css_class = "list-panel-v4-qualification"
    color_result_field = "status_label"
    result_success_values = ("正常", "在用", "有效", "生效")
    result_failure_values = ("停用", "失效", "过期")

    def _base_queryset(self):
        return super().get_queryset().annotate(purchase_detail_count=Count("purchase_details"))

    def get_queryset(self):
        queryset = self._base_queryset()
        status_filter = self.request.GET.get("status", "").strip()
        expiry_scope = self.request.GET.get("expiry_scope", "").strip().lower()
        today = timezone.localdate()
        within_30_days = today + timedelta(days=30)

        if status_filter == "__empty__":
            queryset = queryset.filter(Q(status__isnull=True) | Q(status__exact=""))
        elif status_filter:
            queryset = queryset.filter(status__iexact=status_filter)

        if expiry_scope == "soon":
            queryset = queryset.filter(
                expire_date__isnull=False,
                expire_date__gte=today,
                expire_date__lte=within_30_days,
            )
        elif expiry_scope == "expired":
            queryset = queryset.filter(
                expire_date__isnull=False,
                expire_date__lt=today,
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = self._base_queryset()
        today = timezone.localdate()
        within_30_days = today + timedelta(days=30)
        expiring_soon_count = base_queryset.filter(expire_date__isnull=False, expire_date__gte=today, expire_date__lte=within_30_days).count()
        expired_count = base_queryset.filter(expire_date__isnull=False, expire_date__lt=today).count()
        active_status_filter = (self.request.GET.get("status", "").strip()).casefold()
        active_expiry_scope = (self.request.GET.get("expiry_scope", "").strip()).casefold()

        context["summary_cards"] = [
            {
                "value": base_queryset.count(),
                "label": "Total",
                "accent_class": "is-primary",
                "icon": "stack",
                "filter_url": self.build_list_url(status="", expiry_scope=""),
                "is_active": not active_status_filter and not active_expiry_scope,
            },
            {
                "value": expiring_soon_count,
                "label": "30天内到期",
                "accent_class": "is-warning",
                "icon": "warning",
                "filter_url": self.build_list_url(expiry_scope="soon"),
                "is_active": active_expiry_scope == "soon",
            },
            {
                "value": expired_count,
                "label": "已过期",
                "accent_class": "is-info",
                "icon": "warning",
                "filter_url": self.build_list_url(expiry_scope="expired"),
                "is_active": active_expiry_scope == "expired",
            },
        ]

        status_rows = (
            base_queryset.values("status")
            .annotate(total=Count("id"))
            .order_by("-total", "status")
        )
        accent_cycle = ["is-success", "is-warning", "is-info"]
        context["summary_cards"] += [
            {
                "value": row["total"],
                "label": row["status"] or "未填写状态",
                "accent_class": accent_cycle[index % len(accent_cycle)],
                "icon": "network",
                "filter_url": self.build_list_url(status="__empty__" if not row["status"] else row["status"]),
                "is_active": (
                    active_status_filter == "__empty__"
                    if not row["status"]
                    else active_status_filter == row["status"].casefold()
                ),
            }
            for index, row in enumerate(status_rows)
        ]
        return context


class QualificationHistoryApiView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "assets.view_qualificationmanagement"

    def _get_target(self, pk):
        return get_object_or_404(QualificationManagement, pk=pk)

    def _serialize_datetime(self, value):
        if not value:
            return {"display": "-", "input": ""}
        dt = timezone.localtime(value) if timezone.is_aware(value) else value
        return {"display": dt.strftime("%Y-%m-%d %H:%M:%S"), "input": dt.strftime("%Y-%m-%dT%H:%M")}

    def _serialize_item(self, detail):
        create_time = self._serialize_datetime(detail.create_time)
        expire_date = self._serialize_datetime(detail.expire_date)
        return {
            "id": detail.id,
            "create_time": create_time["display"],
            "create_time_input": create_time["input"],
            "cost_amount": str(detail.cost_amount if detail.cost_amount is not None else "0"),
            "expire_date": expire_date["display"],
            "expire_date_input": expire_date["input"],
            "remark": detail.remark or "",
        }

    def _payload(self, qualification):
        details = PurchaseDetail.objects.filter(parent_id=qualification.pk).order_by("-create_time", "-id")
        return {
            "qualification": {
                "id": qualification.pk,
                "qualification_name": qualification.qualification_name or "-",
                "qualification_category": qualification.qualification_category or "-",
                "status": qualification.status or "-",
                "expire_date": qualification.expire_date.strftime("%Y-%m-%d") if qualification.expire_date else "-",
            },
            "history": [self._serialize_item(item) for item in details],
        }

    def _check_perm(self, request, *permissions):
        return request.user.is_superuser or any(request.user.has_perm(item) for item in permissions)

    def _parse_datetime(self, raw_value, *, required=False):
        value = (raw_value or "").strip()
        if not value:
            if required:
                raise ValueError("时间不能为空")
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            raise ValueError("时间格式不正确")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def _parse_cost(self, raw_value):
        value = (raw_value or "").strip()
        if not value:
            return Decimal("0.00")
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            raise ValueError("成本金额格式不正确")

    def get(self, request, pk, *args, **kwargs):
        qualification = self._get_target(pk)
        return JsonResponse(self._payload(qualification))

    def post(self, request, pk, *args, **kwargs):
        qualification = self._get_target(pk)
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "请求格式不正确"}, status=400)

        action = (data.get("action") or "").strip().lower()
        if action not in {"add", "update", "delete"}:
            return JsonResponse({"error": "不支持的操作"}, status=400)

        if action == "add" and not self._check_perm(request, "assets.add_purchasedetail", "assets.change_qualificationmanagement"):
            return JsonResponse({"error": "无权限新增记录"}, status=403)
        if action == "update" and not self._check_perm(request, "assets.change_purchasedetail", "assets.change_qualificationmanagement"):
            return JsonResponse({"error": "无权限修改记录"}, status=403)
        if action == "delete" and not self._check_perm(request, "assets.delete_purchasedetail", "assets.change_qualificationmanagement"):
            return JsonResponse({"error": "无权限删除记录"}, status=403)

        try:
            if action == "add":
                create_time = self._parse_datetime(data.get("create_time"), required=False) or timezone.now()
                cost_amount = self._parse_cost(data.get("cost_amount"))
                expire_date = self._parse_datetime(data.get("expire_date"), required=False)
                remark = (data.get("remark") or "").strip() or None
                PurchaseDetail.objects.create(
                    parent_id=qualification.pk,
                    create_time=create_time,
                    cost_amount=cost_amount,
                    expire_date=expire_date,
                    remark=remark,
                )
            elif action == "update":
                detail_id = data.get("detail_id")
                if not detail_id:
                    raise ValueError("缺少记录ID")
                detail = get_object_or_404(PurchaseDetail, pk=detail_id, parent_id=qualification.pk)
                detail.create_time = self._parse_datetime(data.get("create_time"), required=False) or timezone.now()
                detail.cost_amount = self._parse_cost(data.get("cost_amount"))
                detail.expire_date = self._parse_datetime(data.get("expire_date"), required=False)
                detail.remark = (data.get("remark") or "").strip() or None
                detail.save(update_fields=["create_time", "cost_amount", "expire_date", "remark"])
            else:
                detail_id = data.get("detail_id")
                if not detail_id:
                    raise ValueError("缺少记录ID")
                detail = get_object_or_404(PurchaseDetail, pk=detail_id, parent_id=qualification.pk)
                detail.delete()
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        sync_qualification_snapshot_from_latest_detail(qualification)
        return JsonResponse(self._payload(qualification))


class _NextUrlMixin:
    def _resolve_next_url(self):
        next_url = self.request.POST.get("next") or self.request.GET.get("next") or ""
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return next_url
        return ""

    def get_success_url(self):
        next_url = self._resolve_next_url()
        if next_url:
            return next_url
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next_url"] = self._resolve_next_url()
        return context


class PurchaseDetailCreateView(_NextUrlMixin, ManagedCreateView):
    model = PurchaseDetail
    form_class = PurchaseDetailManageForm
    permission_required = "assets.add_purchasedetail"
    page_title = "新增修改记录"
    success_url = reverse_lazy("assets:qualification-list")

    def dispatch(self, request, *args, **kwargs):
        self.qualification = get_object_or_404(QualificationManagement, pk=kwargs.get("qualification_pk"))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.parent = self.qualification
        with transaction.atomic():
            response = super().form_valid(form)
            sync_qualification_snapshot_from_latest_detail(self.qualification)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"新增修改记录 · {self.qualification.qualification_name or self.qualification.pk}"
        return context


class PurchaseDetailUpdateView(_NextUrlMixin, ManagedUpdateView):
    model = PurchaseDetail
    form_class = PurchaseDetailManageForm
    permission_required = "assets.change_purchasedetail"
    page_title = "编辑修改记录"
    success_url = reverse_lazy("assets:qualification-list")

    def post(self, request, *args, **kwargs):
        if request.POST.get("_action") == "delete":
            return self._delete_detail(request)
        return super().post(request, *args, **kwargs)

    def _delete_detail(self, request):
        if not request.user.has_perm("assets.delete_purchasedetail"):
            raise PermissionDenied

        target = self.get_object()
        try:
            target.delete()
        except Exception:
            log_operation(
                user=request.user,
                module=self.model._meta.app_label,
                action="delete",
                target=target,
                request=request,
                result="failed",
            )
            raise

        log_operation(
            user=request.user,
            module=self.model._meta.app_label,
            action="delete",
            target=target,
            request=request,
            result="success",
        )
        if target.parent_id:
            sync_qualification_snapshot_from_latest_detail(target.parent)
        messages.success(request, "修改记录已删除。")
        return redirect(self.get_success_url())

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            if self.object and self.object.parent_id:
                sync_qualification_snapshot_from_latest_detail(self.object.parent)
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        name = self.object.parent.qualification_name if self.object and self.object.parent_id else ""
        context["page_title"] = f"编辑修改记录 · {name or self.object.parent_id}"
        context["show_delete_button"] = self.request.user.has_perm("assets.delete_purchasedetail")
        context["submit_after_delete"] = True
        context["submit_label"] = "保存"
        context["delete_label"] = "删除"
        context["delete_confirm_text"] = "确认删除这条修改记录吗？"
        return context


class QualificationFormsetMixin:
    detail_formset_class = PurchaseDetailFormSet
    detail_formset_prefix = "details"

    def get_detail_formset(self, data=None):
        kwargs = {"prefix": self.detail_formset_prefix}
        if data is not None:
            kwargs["data"] = data
        if getattr(self, "object", None) is not None:
            kwargs["instance"] = self.object
        return self.detail_formset_class(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["detail_formset"] = kwargs.get("detail_formset") or self.get_detail_formset()
        return context

    def sync_parent_snapshot_from_formset(self, detail_formset):
        if not detail_formset.has_changed():
            return
        if detail_formset.instance and detail_formset.instance.pk:
            sync_qualification_snapshot_from_latest_detail(detail_formset.instance)


class QualificationManagementCreateView(QualificationFormsetMixin, ManagedCreateView):
    model = QualificationManagement
    form_class = QualificationManagementForm
    permission_required = "assets.add_qualificationmanagement"
    template_name = "assets/qualification_form.html"
    page_title = "新增资质"
    success_url = reverse_lazy("assets:qualification-list")

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        detail_formset = self.get_detail_formset(data=request.POST)
        if form.is_valid() and detail_formset.is_valid():
            return self.forms_valid(form, detail_formset)
        return self.forms_invalid(form, detail_formset)

    def forms_valid(self, form, detail_formset):
        with transaction.atomic():
            response = super().form_valid(form)
            detail_formset.instance = self.object
            detail_formset.save()
            self.sync_parent_snapshot_from_formset(detail_formset)
        return response

    def forms_invalid(self, form, detail_formset):
        return self.render_to_response(self.get_context_data(form=form, detail_formset=detail_formset))


class QualificationManagementUpdateView(QualificationFormsetMixin, ManagedUpdateView):
    model = QualificationManagement
    form_class = QualificationManagementForm
    permission_required = "assets.change_qualificationmanagement"
    template_name = "assets/qualification_form.html"
    page_title = "编辑资质"
    success_url = reverse_lazy("assets:qualification-list")

    def post(self, request, *args, **kwargs):
        if request.POST.get("_action") == "delete":
            return self._delete_qualification(request)

        self.object = self.get_object()
        form = self.get_form()
        detail_formset = self.get_detail_formset(data=request.POST)
        if form.is_valid() and detail_formset.is_valid():
            return self.forms_valid(form, detail_formset)
        return self.forms_invalid(form, detail_formset)

    def forms_valid(self, form, detail_formset):
        with transaction.atomic():
            response = super().form_valid(form)
            detail_formset.instance = self.object
            detail_formset.save()
            self.sync_parent_snapshot_from_formset(detail_formset)
        return response

    def forms_invalid(self, form, detail_formset):
        return self.render_to_response(self.get_context_data(form=form, detail_formset=detail_formset))

    def _delete_qualification(self, request):
        if not request.user.has_perm("assets.delete_qualificationmanagement"):
            raise PermissionDenied

        target = self.get_object()
        try:
            target.delete()
        except Exception:
            log_operation(
                user=request.user,
                module=self.model._meta.app_label,
                action="delete",
                target=target,
                request=request,
                result="failed",
            )
            raise

        log_operation(
            user=request.user,
            module=self.model._meta.app_label,
            action="delete",
            target=target,
            request=request,
            result="success",
        )
        messages.success(request, "资质记录已删除。")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_delete_button"] = self.request.user.has_perm("assets.delete_qualificationmanagement")
        context["submit_label"] = "保存"
        context["delete_label"] = "删除"
        context["delete_confirm_text"] = "确认删除这条资质记录吗？相关修改记录也会一并删除。"
        return context


