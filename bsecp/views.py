import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from bsecp.forms import AuthorizationRecordForm, ModuleForm
from bsecp.models import AuthorizationRecord, Module
from bsecp.mysql_auth import (
    fetch_authorization_customer_suggestions,
    fetch_authorization_detail_sets,
    fetch_module_rows,
)
from bsecp.sqlserver_auth import (
    fetch_authorization_record_rows,
    fetch_authorization_record_summary,
)
from core.views import ManagedCreateView, ManagedUpdateView, SearchableListView

logger = logging.getLogger(__name__)


class ModuleListView(SearchableListView):
    template_name = "bsecp/module_list.html"
    model = Module
    permission_required = "bsecp.view_module"
    paginate_by = 12
    paginate_by_options = [12, 24, 48]
    page_title = "Module 管理"
    page_description = "展示 cljc_module 表中的模块信息。"
    search_fields = [
        "md_code",
        "md_name",
        "md_productcode",
        "md_remark",
        "md_forbit_user",
        "md_create_user",
        "md_modify_user",
    ]
    columns = [
        ("MD_CODE", "md_code"),
        ("MD_NAME", "md_name"),
        ("MD_PRODUCTID", "md_productid"),
        ("MD_PRODUCTCODE", "md_productcode"),
        ("MD_ISPOINT", "md_ispoint"),
        ("MD_PRICE", "md_price"),
        ("MD_STATE", "md_state"),
        ("MD_REMARK", "md_remark"),
    ]
    create_url_name = "bsecp:module-create"
    edit_url_name = "bsecp:module-edit"

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        try:
            return fetch_module_rows(search_text=query)
        except Exception:
            logger.exception("Failed to load module rows from MYSQL_AUTH datasource.")
            messages.error(self.request, "Module 数据源查询失败，请检查 MYSQL_AUTH 连接配置。")
            return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visible_count = len(context.get("object_list", []))
        remainder = visible_count % 4
        context["module_placeholder_count"] = 0 if visible_count == 0 or remainder == 0 else 4 - remainder
        return context


class ModuleCreateView(ManagedCreateView):
    model = Module
    form_class = ModuleForm
    permission_required = "bsecp.add_module"
    page_title = "新增 Module"
    success_url = reverse_lazy("bsecp:module-list")


class ModuleUpdateView(ManagedUpdateView):
    model = Module
    form_class = ModuleForm
    permission_required = "bsecp.change_module"
    page_title = "编辑 Module"
    success_url = reverse_lazy("bsecp:module-list")


class AuthorizationRecordListView(SearchableListView):
    model = AuthorizationRecord
    permission_required = "bsecp.view_authorizationrecord"
    page_title = "授权查询"
    page_description = "查询本地库中的授权记录。"
    search_fields = [
        "OD_SERIAL_NUMBER",
        "OD_CONTRACT_NUMBER",
        "OD_BMPID",
        "AutoAuthFlag",
        "AutoAuthHandleResult",
        "Remark",
        "AutoAuthHandleResultDesc",
    ]
    columns = [
        ("Order Serial Number", "OD_SERIAL_NUMBER"),
        ("Contract Number", "OD_CONTRACT_NUMBER"),
        ("Create Time", "CreateTime"),
        ("Handle Time", "AutoAuthHandleTime"),
        ("Handle Result", "AutoAuthHandleResult"),
        ("Handle Result Desc", "AutoAuthHandleResultDesc"),
    ]
    color_result_field = "AutoAuthHandleResult"
    result_success_values = ("success", "成功", "自动化授权成功")
    result_failure_values = ("fail", "失败", "自动化授权失败")
    create_url_name = ""
    edit_url_name = ""
    show_actions = False
    panel_css_class = "list-panel-v4-authq"
    paginate_by = 20
    paginate_by_options = [20, 50, 100]
    summary_filter_param = "summary"
    summary_filter_options = (
        "total_success",
        "total_failure",
        "today_success",
        "today_failure",
    )

    def _normalize_text(self, value):
        return str(value or "").strip().lower()

    def _resolve_result_bucket(self, value):
        normalized = self._normalize_text(value)
        if not normalized:
            return ""
        success_tokens = [self._normalize_text(token) for token in self.result_success_values]
        failure_tokens = [self._normalize_text(token) for token in self.result_failure_values]
        if any(token and token in normalized for token in success_tokens):
            return "success"
        if any(token and token in normalized for token in failure_tokens):
            return "failure"
        return ""

    def _to_local_date(self, value):
        if not value:
            return None
        if timezone.is_aware(value):
            return timezone.localtime(value).date()
        if hasattr(value, "date"):
            return value.date()
        return None

    def _active_summary_filter(self):
        raw_value = self.request.GET.get(self.summary_filter_param, "")
        normalized = self._normalize_text(raw_value)
        return normalized if normalized in self.summary_filter_options else ""

    def _matches_summary_filter(self, row, summary_filter):
        if not summary_filter:
            return True

        bucket = self._resolve_result_bucket(getattr(row, "AutoAuthHandleResult", None))
        handle_date = self._to_local_date(getattr(row, "AutoAuthHandleTime", None))
        is_today = handle_date == timezone.localdate()

        if summary_filter == "total_success":
            return bucket == "success"
        if summary_filter == "total_failure":
            return bucket == "failure"
        if summary_filter == "today_success":
            return bucket == "success" and is_today
        if summary_filter == "today_failure":
            return bucket == "failure" and is_today
        return True

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        active_summary_filter = self._active_summary_filter()
        try:
            rows = fetch_authorization_record_rows(search_text=query)
        except Exception:
            logger.exception("Failed to load authorization queue rows from SQL Server datasource.")
            messages.error(self.request, "授权查询 SQL Server 查询失败，请检查 SQLSERVER_AUTH 连接配置。")
            return []
        return [row for row in rows if self._matches_summary_filter(row, active_summary_filter)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_summary_filter = self._active_summary_filter()
        summary = {
            "total_success": 0,
            "total_failure": 0,
            "today_success": 0,
            "today_failure": 0,
        }
        try:
            summary = fetch_authorization_record_summary(
                success_values=self.result_success_values,
                failure_values=self.result_failure_values,
            )
        except Exception:
            logger.exception("Failed to load authorization queue summary from SQL Server datasource.")
            messages.error(self.request, "授权查询统计 SQL Server 查询失败，请检查 SQLSERVER_AUTH 连接配置。")

        context["summary_cards"] = [
            {
                "value": summary["total_success"],
                "label": "Total Success",
                "accent_class": "is-success",
                "icon": "success",
                "filter_url": self.build_list_url(summary="" if active_summary_filter == "total_success" else "total_success"),
                "is_active": active_summary_filter == "total_success",
            },
            {
                "value": summary["total_failure"],
                "label": "Total Failure",
                "accent_class": "is-warning",
                "icon": "warning",
                "filter_url": self.build_list_url(summary="" if active_summary_filter == "total_failure" else "total_failure"),
                "is_active": active_summary_filter == "total_failure",
            },
            {
                "value": summary["today_success"],
                "label": "Today Success",
                "accent_class": "is-info",
                "icon": "success",
                "filter_url": self.build_list_url(summary="" if active_summary_filter == "today_success" else "today_success"),
                "is_active": active_summary_filter == "today_success",
            },
            {
                "value": summary["today_failure"],
                "label": "Today Failure",
                "accent_class": "is-primary",
                "icon": "warning",
                "filter_url": self.build_list_url(summary="" if active_summary_filter == "today_failure" else "today_failure"),
                "is_active": active_summary_filter == "today_failure",
            },
        ]
        return context


class AuthorizationDetailListView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "bsecp/authorization_detail.html"
    permission_required = "bsecp.view_authorizationrecord"
    page_title = "授权详情"
    page_description = "按客户名称模糊查询，分表展示 cljc_customer / cljc_license / cljc_licensedetail。"

    customer_columns = [
        ("客户ID", "CU_ID"),
        ("源代码", "CU_SRCCODE"),
        ("组织代码", "CU_ORGCODE"),
        ("客户代码", "CU_CODE"),
        ("客户名称", "CU_NAME"),
        ("状态", "CU_STATE"),
        ("创建日期", "CU_CREATE_DATE"),
    ]

    license_columns = [
        ("授权ID", "LIC_ID"),
        ("许可证ID", "LIC_LICENSEID"),
        ("账号", "LIC_ACCOUNT"),
        ("许可证信息", "LIC_LICENSEINFO"),
        ("密码", "LIC_PASSWORD"),
        ("客户ID", "LIC_CUID"),
        ("客户名称", "LIC_CUNAME"),
        ("序列号", "LIC_SERIAL"),
        ("订单ID", "LIC_ORDERID"),
        ("产品类型ID", "LIC_PTID"),
        ("类型", "LIC_TYPE"),
        ("类型信息", "LIC_TYPEINFO"),
        ("激活", "LIC_ACTIVE"),
        ("开始日期", "LIC_START"),
        ("结束日期", "LIC_END"),
        ("绑定", "LIC_BIND"),
        ("状态", "LIC_STATE"),
        ("订单号", "LIC_ORDERNUMBER"),
        ("BMP单号", "LIC_BMP_NUMBER"),
    ]

    licensedetail_columns = [
        ("ID", "LICD_ID"),
        ("主ID", "LICD_MAINID"),
        ("客户名称", "LICD_SRCCUNAME"),
        ("客户ID", "LICD_INCUID"),
        ("产品ID", "LICD_PTID"),
        ("产品名称", "LICD_PTNAME"),
        ("模块ID", "LICD_MDID"),
        ("模块名称", "LICD_MDNAME"),
        ("数量", "LICD_COUNT"),
        ("类型", "LICD_TYPE"),
        ("类型信息", "LICD_TYPEINFO"),
        ("开始日期", "LICD_START"),
        ("结束日期", "LICD_END"),
        ("创建日期", "LICD_CREATE_DATE"),
        ("修改日期", "LICD_MODIFY_DATE"),
        ("状态", "LICD_STATE"),
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        context.update(
            {
                "page_title": self.page_title,
                "page_description": self.page_description,
                "query": query,
                "customer_columns": self.customer_columns,
                "license_columns": self.license_columns,
                "licensedetail_columns": self.licensedetail_columns,
                "customer_rows": [],
                "license_rows": [],
                "licensedetail_rows": [],
            }
        )

        if not query:
            return context

        try:
            result = fetch_authorization_detail_sets(customer_name=query)
            context["customer_rows"] = result["customer_rows"]
            context["license_rows"] = result["license_rows"]
            context["licensedetail_rows"] = result["licensedetail_rows"]
        except Exception:
            logger.exception("Failed to load authorization detail datasets from external MySQL.")
            messages.error(self.request, "授权详情 MySQL 查询失败，请检查连接配置或联系管理员。")

        return context


class AuthorizationDetailSuggestView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "bsecp.view_authorizationrecord"

    def get(self, request, *args, **kwargs):
        keyword = request.GET.get("q", "").strip()
        if not keyword:
            return JsonResponse({"items": []})
        try:
            rows = fetch_authorization_customer_suggestions(keyword=keyword, limit=12)
        except Exception:
            logger.exception("Failed to load authorization customer suggestions from external MySQL.")
            return JsonResponse({"items": []})
        return JsonResponse(
            {
                "items": [
                    {
                        "name": row.CU_NAME or "-",
                        "code": row.CU_CODE or "-",
                        "org_code": row.CU_ORGCODE or "-",
                    }
                    for row in rows
                ]
            }
        )


class AuthorizationRecordCreateView(ManagedCreateView):
    model = AuthorizationRecord
    form_class = AuthorizationRecordForm
    permission_required = "bsecp.add_authorizationrecord"
    page_title = "Create Authorization Queue Record"
    success_url = reverse_lazy("bsecp:authorization-list")


class AuthorizationRecordUpdateView(ManagedUpdateView):
    model = AuthorizationRecord
    form_class = AuthorizationRecordForm
    permission_required = "bsecp.change_authorizationrecord"
    page_title = "Edit Authorization Queue Record"
    success_url = reverse_lazy("bsecp:authorization-list")
