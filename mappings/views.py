from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy

from core.views import ManagedCreateView, ManagedUpdateView, SearchableListView
from logs.utils import log_operation, log_resource_change_by_type
from mappings.forms import PortMappingForm
from mappings.models import DNSRecord, PortMapping
from mappings.services import (
    H3CNatApplyError,
    H3CNatSyncError,
    apply_h3c_nat_mapping,
    remove_h3c_nat_mapping,
    sync_h3c_nat_mappings,
)

PORT_MAPPING_CHANGED_FIELDS = [
    "interface",
    "protocol",
    "public_ip",
    "public_port",
    "private_ip",
    "private_port",
]


def _build_port_mapping_snapshot(payload):
    return {field: payload.get(field) for field in PORT_MAPPING_CHANGED_FIELDS}


def _find_port_mapping_pk(payload):
    query = {field: payload.get(field) for field in PORT_MAPPING_CHANGED_FIELDS}
    matched = PortMapping.objects.filter(**query).order_by("-updated_at", "-id").first()
    return str(matched.pk) if matched else ""


def _fallback_port_mapping_resource_id(payload):
    return f"rule:{payload.get('public_ip')}:{payload.get('public_port')}->{payload.get('private_ip')}:{payload.get('private_port')}"


class PortMappingListView(SearchableListView):
    model = PortMapping
    permission_required = "mappings.view_portmapping"
    page_title = "端口映射"
    page_description = "展示 NAT 端口映射规则（公网到内网）。"
    search_fields = ["interface", "protocol", "public_ip", "private_ip", "private_port"]
    columns = [
        ("网络接口", "interface"),
        ("协议", "protocol"),
        ("公网IP", "public_ip"),
        ("公网端口", "public_port"),
        ("内网IP", "private_ip"),
        ("内网端口", "private_port"),
        ("更新时间", "updated_at"),
    ]
    create_url_name = "mappings:port-create"
    edit_url_name = "mappings:port-edit"
    panel_css_class = "list-panel-v4-portmap"

    def _base_queryset(self):
        if not hasattr(self, "_base_queryset_cache"):
            self._sync_from_h3c_if_requested()
            self._base_queryset_cache = super().get_queryset()
        return self._base_queryset_cache

    def _sync_force_requested(self):
        return self.request.GET.get("sync", "").strip().lower() in {"1", "true", "yes", "on"}

    def _sync_from_h3c_if_requested(self):
        if not self._sync_force_requested():
            return

        try:
            result = sync_h3c_nat_mappings()
        except H3CNatSyncError as exc:
            messages.warning(self.request, f"H3C 同步失败，当前展示数据库缓存数据：{exc}")
            return

        messages.success(self.request, f"H3C 同步完成：{result['total']} 条映射。")

    def get_queryset(self):
        queryset = self._base_queryset()
        interface_filter = self.request.GET.get("interface", "").strip()
        if interface_filter == "__empty__":
            queryset = queryset.filter(Q(interface__isnull=True) | Q(interface__exact=""))
        elif interface_filter:
            queryset = queryset.filter(interface__iexact=interface_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_interface_filter = (self.request.GET.get("interface", "").strip()).casefold()
        params = self.request.GET.copy()
        params["sync"] = "1"
        query = params.urlencode()
        context["sync_url"] = f"{self.request.path}?{query}" if query else f"{self.request.path}?sync=1"
        context["sync_label"] = "手动同步"
        accent_cycle = ["is-primary", "is-success", "is-warning"]
        base_queryset = self._base_queryset()
        total_count = base_queryset.count()
        interface_rows = (
            base_queryset.values("interface")
            .annotate(total=Count("id"))
            .order_by("interface")
        )
        context["summary_cards"] = [
            {
                "value": total_count,
                "label": "Total",
                "accent_class": "is-primary",
                "icon": "network",
                "filter_url": self.build_list_url(interface="", sync=""),
                "is_active": not active_interface_filter,
            },
        ] + [
            {
                "value": row["total"],
                "label": row["interface"] or "未填写",
                "accent_class": accent_cycle[(index + 1) % len(accent_cycle)],
                "icon": "network",
                "filter_url": self.build_list_url(interface="__empty__" if not row["interface"] else row["interface"], sync=""),
                "is_active": (
                    active_interface_filter == "__empty__"
                    if not row["interface"]
                    else active_interface_filter == row["interface"].casefold()
                ),
            }
            for index, row in enumerate(interface_rows)
        ]
        return context


class PortMappingCreateView(ManagedCreateView):
    model = PortMapping
    form_class = PortMappingForm
    permission_required = "mappings.add_portmapping"
    page_title = "新增端口映射"
    success_url = reverse_lazy("mappings:port-list")

    def form_valid(self, form):
        data = form.cleaned_data
        payload = {
            "interface": str(data["interface"]).strip(),
            "protocol": str(data["protocol"]).strip(),
            "public_ip": str(data["public_ip"]).strip(),
            "public_port": str(data["public_port"]).strip(),
            "private_ip": str(data["private_ip"]).strip(),
            "private_port": str(data["private_port"]).strip(),
        }
        try:
            apply_h3c_nat_mapping(**payload)
        except H3CNatApplyError as exc:
            log_operation(
                user=self.request.user,
                module=self.model._meta.app_label,
                action="create",
                target=None,
                request=self.request,
                result="failed",
            )
            form.add_error(None, f"H3C 下发失败：{exc}")
            return self.form_invalid(form)

        sync_warning = ""
        try:
            sync_h3c_nat_mappings()
        except H3CNatSyncError as exc:
            sync_warning = str(exc)
            messages.warning(self.request, f"配置已下发成功，但回拉同步失败：{exc}")
        else:
            messages.success(self.request, "端口映射已下发到 H3C 并同步到列表。")

        resource_id = _find_port_mapping_pk(payload) or _fallback_port_mapping_resource_id(payload)
        target_obj = PortMapping.objects.filter(**payload).order_by("-updated_at", "-id").first()
        log_operation(
            user=self.request.user,
            module=self.model._meta.app_label,
            action="create",
            target=target_obj,
            request=self.request,
            result="warning" if sync_warning else "success",
        )
        log_resource_change_by_type(
            resource_type=PortMapping._meta.label,
            resource_id=resource_id,
            action="created",
            before_snapshot={},
            after_snapshot=_build_port_mapping_snapshot(payload),
            changed_fields=list(PORT_MAPPING_CHANGED_FIELDS),
        )

        return redirect(self.get_success_url())


class PortMappingUpdateView(ManagedUpdateView):
    model = PortMapping
    form_class = PortMappingForm
    permission_required = "mappings.change_portmapping"
    page_title = "编辑端口映射"
    success_url = reverse_lazy("mappings:port-list")

    def post(self, request, *args, **kwargs):
        if request.POST.get("_action") == "delete":
            return self._delete_mapping(request)
        return super().post(request, *args, **kwargs)

    def _mapping_payload_from_instance(self, obj):
        return {
            "interface": str(obj.interface).strip(),
            "protocol": str(obj.protocol).strip(),
            "public_ip": str(obj.public_ip).strip(),
            "public_port": str(obj.public_port).strip(),
            "private_ip": str(obj.private_ip).strip(),
            "private_port": str(obj.private_port).strip(),
        }

    def _mapping_payload_from_cleaned_data(self, cleaned_data):
        return {
            "interface": str(cleaned_data["interface"]).strip(),
            "protocol": str(cleaned_data["protocol"]).strip(),
            "public_ip": str(cleaned_data["public_ip"]).strip(),
            "public_port": str(cleaned_data["public_port"]).strip(),
            "private_ip": str(cleaned_data["private_ip"]).strip(),
            "private_port": str(cleaned_data["private_port"]).strip(),
        }

    def form_valid(self, form):
        old_obj = self.get_object()
        old_payload = self._mapping_payload_from_instance(old_obj)
        new_payload = self._mapping_payload_from_cleaned_data(form.cleaned_data)
        changed_fields = [field for field in PORT_MAPPING_CHANGED_FIELDS if old_payload.get(field) != new_payload.get(field)]

        if old_payload == new_payload:
            messages.info(self.request, "未检测到变更，无需下发。")
            return redirect(self.get_success_url())

        try:
            remove_h3c_nat_mapping(**old_payload)
        except H3CNatApplyError as exc:
            log_operation(
                user=self.request.user,
                module=self.model._meta.app_label,
                action="update",
                target=old_obj,
                request=self.request,
                result="failed",
            )
            form.add_error(None, f"H3C 撤销旧规则失败：{exc}")
            return self.form_invalid(form)

        try:
            apply_h3c_nat_mapping(**new_payload)
        except H3CNatApplyError as exc:
            rollback_error = ""
            try:
                apply_h3c_nat_mapping(**old_payload)
            except H3CNatApplyError as rollback_exc:
                rollback_error = str(rollback_exc)

            log_operation(
                user=self.request.user,
                module=self.model._meta.app_label,
                action="update",
                target=old_obj,
                request=self.request,
                result="failed",
            )
            if rollback_error:
                form.add_error(None, f"H3C 下发新规则失败：{exc}；旧规则回滚失败：{rollback_error}。请人工检查。")
            else:
                form.add_error(None, f"H3C 下发新规则失败：{exc}；已自动恢复旧规则。")
            return self.form_invalid(form)

        sync_warning = ""
        try:
            sync_h3c_nat_mappings()
        except H3CNatSyncError as exc:
            sync_warning = str(exc)
            PortMapping.objects.filter(pk=old_obj.pk).update(**new_payload)

        log_operation(
            user=self.request.user,
            module=self.model._meta.app_label,
            action="update",
            target=old_obj,
            request=self.request,
            result="success",
        )
        log_resource_change_by_type(
            resource_type=PortMapping._meta.label,
            resource_id=str(old_obj.pk),
            action="updated",
            before_snapshot=_build_port_mapping_snapshot(old_payload),
            after_snapshot=_build_port_mapping_snapshot(new_payload),
            changed_fields=changed_fields,
        )
        if sync_warning:
            messages.warning(self.request, f"端口映射已先撤销旧规则并下发新规则，但回拉同步失败：{sync_warning}")
        else:
            messages.success(self.request, "端口映射已更新：先撤销旧规则，再下发新规则，并完成同步。")
        return redirect(self.get_success_url())

    def _delete_mapping(self, request):
        if not request.user.has_perm("mappings.delete_portmapping"):
            raise PermissionDenied

        target = self.get_object()
        old_payload = self._mapping_payload_from_instance(target)
        try:
            remove_h3c_nat_mapping(**old_payload)
        except H3CNatApplyError as exc:
            log_operation(
                user=request.user,
                module=self.model._meta.app_label,
                action="delete",
                target=target,
                request=request,
                result="failed",
            )
            messages.error(request, f"H3C undo 失败：{exc}")
            return redirect(request.path)

        sync_warning = ""
        try:
            sync_h3c_nat_mappings()
        except H3CNatSyncError as exc:
            sync_warning = str(exc)
            table_name = connection.ops.quote_name(PortMapping._meta.db_table)
            pk_name = connection.ops.quote_name(PortMapping._meta.pk.column)
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {table_name} WHERE {pk_name} = %s", [target.pk])

        log_operation(
            user=request.user,
            module=self.model._meta.app_label,
            action="delete",
            target=target,
            request=request,
            result="success",
        )
        log_resource_change_by_type(
            resource_type=PortMapping._meta.label,
            resource_id=str(target.pk),
            action="deleted",
            before_snapshot=_build_port_mapping_snapshot(old_payload),
            after_snapshot={},
            changed_fields=list(PORT_MAPPING_CHANGED_FIELDS),
        )
        if sync_warning:
            messages.warning(request, f"端口映射已在 H3C 撤销并从本地删除，但回拉同步失败：{sync_warning}")
        else:
            messages.success(request, "端口映射已撤销（undo）并同步完成。")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_delete_button"] = self.request.user.has_perm("mappings.delete_portmapping")
        context["delete_label"] = "删除（Undo）"
        context["delete_confirm_text"] = "确认撤销并删除这条端口映射吗？"
        return context


class DomainMappingListView(SearchableListView):
    model = DNSRecord
    permission_required = "mappings.view_domainmapping"
    page_title = "域名映射"
    page_description = "展示 MySQL 表 dns_records_all 中的 DNS 记录。"
    search_fields = ["platform", "domain_name", "sub_domain", "record_value", "record_line", "raw_id"]
    columns = [
        ("平台", "platform_label"),
        ("域名", "fqdn"),
        ("类型", "record_type"),
        ("线路", "record_line"),
        ("记录值", "record_value"),
        ("状态", "status_label"),
        ("更新时间", "updated_at"),
    ]
    show_actions = False
    create_url_name = ""
    edit_url_name = ""
    panel_css_class = "list-panel-v4-domainmap"
    color_result_field = "status_label"
    result_success_values = ("启用",)
    result_failure_values = ("停用",)

    def _enabled_filter(self):
        return (
            Q(status__iexact="enable")
            | Q(status__iexact="enabled")
            | Q(status__iexact="启用")
        )

    def _disabled_filter(self):
        return (
            Q(status__iexact="disable")
            | Q(status__iexact="disabled")
            | Q(status__iexact="停用")
        )

    def _base_queryset(self):
        return super().get_queryset()

    def get_queryset(self):
        queryset = self._base_queryset()
        status_scope = self.request.GET.get("status_scope", "").strip().lower()
        platform_scope = self.request.GET.get("platform_scope", "").strip().lower()
        if status_scope == "enabled":
            queryset = queryset.filter(self._enabled_filter())
        elif status_scope == "disabled":
            queryset = queryset.filter(self._disabled_filter())
        if platform_scope:
            queryset = queryset.filter(platform__iexact=platform_scope)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self._base_queryset()
        total_count = queryset.count()
        enabled_count = queryset.filter(self._enabled_filter()).count()
        disabled_count = queryset.filter(self._disabled_filter()).count()
        active_status_scope = (self.request.GET.get("status_scope", "").strip()).lower()
        active_platform_scope = (self.request.GET.get("platform_scope", "").strip()).lower()

        platform_rows = queryset.values("platform").annotate(total=Count("id"))
        platform_dnsdjcn = 0
        platform_alidns = 0
        for row in platform_rows:
            raw = (row.get("platform") or "").strip().lower()
            if raw == "dnsdjcn":
                platform_dnsdjcn += row["total"]
            elif raw == "alidns":
                platform_alidns += row["total"]

        context["summary_cards"] = [
            {
                "value": total_count,
                "label": "域名映射总数",
                "accent_class": "is-primary",
                "icon": "globe",
                "filter_url": self.build_list_url(status_scope="", platform_scope=""),
                "is_active": not active_status_scope and not active_platform_scope,
            },
            {
                "value": enabled_count,
                "label": "启用",
                "accent_class": "is-success",
                "icon": "success",
                "filter_url": self.build_list_url(status_scope="enabled", platform_scope=""),
                "is_active": active_status_scope == "enabled" and not active_platform_scope,
            },
            {
                "value": disabled_count,
                "label": "停用",
                "accent_class": "is-warning",
                "icon": "warning",
                "filter_url": self.build_list_url(status_scope="disabled", platform_scope=""),
                "is_active": active_status_scope == "disabled" and not active_platform_scope,
            },
            {
                "value": platform_dnsdjcn,
                "label": "数字引擎",
                "accent_class": "is-info",
                "icon": "stack",
                "filter_url": self.build_list_url(status_scope="", platform_scope="dnsdjcn"),
                "is_active": active_platform_scope == "dnsdjcn" and not active_status_scope,
            },
            {
                "value": platform_alidns,
                "label": "阿里云",
                "accent_class": "is-primary",
                "icon": "network",
                "filter_url": self.build_list_url(status_scope="", platform_scope="alidns"),
                "is_active": active_platform_scope == "alidns" and not active_status_scope,
            },
        ]
        return context
