from __future__ import annotations

import csv
import json
import logging
from datetime import date
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from cloudops.services import (
    JumpServerAPIError,
    extract_first_credential_id,
    extract_user_id,
    get_jumpserver_client,
)
from logs.utils import log_operation

logger = logging.getLogger(__name__)


class BastionHostListView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "cloudops/bastion_list.html"
    permission_required = "cloudops.view_bastionhost"
    page_title = "堡垒机清单"
    page_description = "查看 JumpServer 主机清单、在线人数、凭据详情，并执行常用运维操作。"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = get_jumpserver_client()

        bootstrap_error = ""
        online_count = 0
        if client.configured:
            try:
                online_count = client.count_online_users()
            except JumpServerAPIError as exc:
                bootstrap_error = str(exc)
            except Exception:
                logger.exception("Failed to fetch JumpServer online count on page init.")
                bootstrap_error = "获取在线人数失败，请稍后重试。"
        else:
            bootstrap_error = "JumpServer API 凭据未配置，请联系管理员配置环境变量。"

        context.update(
            {
                "page_title": self.page_title,
                "page_description": self.page_description,
                "online_count": online_count,
                "bootstrap_error": bootstrap_error,
                "config_ready": client.configured,
                "default_cloud_id": client.config.default_cloud_id,
                "api_summary_url": reverse("cloudops:bastion-summary-api"),
                "api_hosts_url": reverse("cloudops:bastion-hosts-api"),
                "api_online_count_url": reverse("cloudops:bastion-online-count-api"),
                "api_export_url": reverse("cloudops:bastion-export-api"),
                "api_ping_url": reverse("cloudops:bastion-ping-api"),
                "api_credentials_url_template": reverse(
                    "cloudops:bastion-credentials-api", kwargs={"host_id": "__HOST_ID__"}
                ),
                "api_restart_url_template": reverse(
                    "cloudops:bastion-restart-api", kwargs={"host_id": "__HOST_ID__"}
                ),
                "api_delete_url_template": reverse(
                    "cloudops:bastion-delete-api", kwargs={"host_id": "__HOST_ID__"}
                ),
                "api_user_info_url_template": reverse(
                    "cloudops:bastion-user-info-api", kwargs={"account": "__ACCOUNT__"}
                ),
                "api_host_user_auth_url": reverse("cloudops:bastion-host-user-auth-api"),
                "api_credential_password_url": reverse("cloudops:bastion-credential-password-api"),
                "ssh_proxy_url": reverse("cloudops:ssh-proxy"),
            }
        )
        return context


class BastionAPIViewBase(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "cloudops.view_bastionhost"

    def _client(self):
        return get_jumpserver_client()

    def _json_ok(self, payload: dict[str, Any] | None = None, *, status: int = 200) -> JsonResponse:
        data = {"success": True}
        if payload:
            data.update(payload)
        return JsonResponse(data, status=status)

    def _json_error(self, message: str, *, status: int = 400, details: str = "") -> JsonResponse:
        data: dict[str, Any] = {"success": False, "error": message}
        if details:
            data["details"] = details[:600]
        return JsonResponse(data, status=status)

    def _handle_exception(self, exc: Exception) -> JsonResponse:
        if isinstance(exc, JumpServerAPIError):
            return self._json_error(str(exc), status=exc.status_code, details=exc.details)
        logger.exception("Unexpected cloudops API error")
        return self._json_error("服务器内部错误", status=500)

    def _load_payload(self, request) -> dict[str, Any]:
        if request.content_type and request.content_type.startswith("application/json"):
            if not request.body:
                return {}
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise JumpServerAPIError("请求体 JSON 格式错误", status_code=400) from exc
            return payload if isinstance(payload, dict) else {}
        return request.POST.dict()

    def _get_cloud_id(self, request, payload: dict[str, Any] | None = None) -> str:
        data = payload or {}
        client = self._client()
        return str(
            request.GET.get("cloud_id")
            or request.POST.get("cloud_id")
            or data.get("cloud_id")
            or data.get("cloudId")
            or client.config.default_cloud_id
        ).strip()

    def _resolve_host_id(self, request, payload: dict[str, Any]) -> str:
        direct_host_id = str(payload.get("hostId") or payload.get("host_id") or "").strip()
        if direct_host_id:
            return direct_host_id

        identifier = str(
            payload.get("host")
            or payload.get("hostKeyword")
            or payload.get("host_keyword")
            or payload.get("hostName")
            or payload.get("host_name")
            or payload.get("hostIp")
            or payload.get("host_ip")
            or ""
        ).strip()
        cloud_id = self._get_cloud_id(request, payload)
        return self._client().resolve_host_id(identifier=identifier, cloud_id=cloud_id)


class BastionSummaryAPIView(BastionAPIViewBase):
    def get(self, request, *args, **kwargs):
        cloud_id = self._get_cloud_id(request)
        force_refresh = request.GET.get("refresh", "").strip().lower() in {"1", "true", "yes", "on"}
        try:
            summary = self._client().get_summary(cloud_id=cloud_id, force_refresh=force_refresh)
        except Exception as exc:
            return self._handle_exception(exc)
        return self._json_ok({"summary": summary})

    def post(self, request, *args, **kwargs):
        payload = self._load_payload(request)
        cloud_id = self._get_cloud_id(request, payload)
        force_refresh = str(payload.get("refresh") or "").strip().lower() in {"1", "true", "yes", "on"}
        try:
            summary = self._client().get_summary(cloud_id=cloud_id, force_refresh=force_refresh)
        except Exception as exc:
            return self._handle_exception(exc)
        return self._json_ok({"summary": summary})


class BastionHostsAPIView(BastionAPIViewBase):
    def get(self, request, *args, **kwargs):
        cloud_id = self._get_cloud_id(request)
        force_refresh = request.GET.get("refresh", "").strip().lower() in {"1", "true", "yes", "on"}
        try:
            hosts = self._client().list_hosts(cloud_id=cloud_id, force_refresh=force_refresh)
        except Exception as exc:
            return self._handle_exception(exc)
        return self._json_ok({"hosts": hosts, "total": len(hosts), "cloud_id": cloud_id})

    def post(self, request, *args, **kwargs):
        payload = self._load_payload(request)
        cloud_id = self._get_cloud_id(request, payload)
        force_refresh = str(payload.get("refresh") or "").strip().lower() in {"1", "true", "yes", "on"}
        try:
            hosts = self._client().list_hosts(cloud_id=cloud_id, force_refresh=force_refresh)
        except Exception as exc:
            return self._handle_exception(exc)
        return self._json_ok({"hosts": hosts, "total": len(hosts), "cloud_id": cloud_id})


class BastionCredentialsAPIView(BastionAPIViewBase):
    def get(self, request, host_id: str, *args, **kwargs):
        force_refresh = request.GET.get("refresh", "").strip().lower() in {"1", "true", "yes", "on"}
        try:
            credentials = self._client().get_credentials(host_id=host_id, force_refresh=force_refresh)
        except Exception as exc:
            return self._handle_exception(exc)
        return self._json_ok({"credentials": credentials})


class BastionOnlineCountAPIView(BastionAPIViewBase):
    def get(self, request, *args, **kwargs):
        try:
            count = self._client().count_online_users()
        except Exception as exc:
            return self._handle_exception(exc)
        return self._json_ok({"count": count})

    def post(self, request, *args, **kwargs):
        try:
            count = self._client().count_online_users()
        except Exception as exc:
            return self._handle_exception(exc)
        return self._json_ok({"count": count})


class BastionExportAPIView(BastionAPIViewBase):
    def get(self, request, *args, **kwargs):
        cloud_id = self._get_cloud_id(request)
        force_refresh = request.GET.get("refresh", "").strip().lower() in {"1", "true", "yes", "on"}

        try:
            hosts = self._client().list_hosts(cloud_id=cloud_id, force_refresh=force_refresh)
        except Exception as exc:
            return self._handle_exception(exc)

        filename = f"jumpserver-hosts-{date.today().isoformat()}.csv"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write("\ufeff")

        writer = csv.writer(response)
        writer.writerow(["主机名", "主机IP", "操作系统", "描述", "Host ID"])
        for host in hosts:
            writer.writerow(
                [
                    host.get("hostName", ""),
                    host.get("hostIp", ""),
                    host.get("operatingSystem", ""),
                    host.get("description", ""),
                    host.get("hostId", ""),
                ]
            )
        return response


class BastionRestartAPIView(BastionAPIViewBase):
    permission_required = "cloudops.change_bastionhost"

    def post(self, request, host_id: str, *args, **kwargs):
        try:
            self._client().restart_host(host_id)
            log_operation(
                user=request.user,
                module="cloudops",
                action="restart_host",
                target=None,
                request=request,
                result="success",
            )
        except Exception as exc:
            log_operation(
                user=request.user,
                module="cloudops",
                action="restart_host",
                target=None,
                request=request,
                result="failed",
            )
            return self._handle_exception(exc)
        return self._json_ok({"message": "重启请求已发送。"})


class BastionDeleteAPIView(BastionAPIViewBase):
    permission_required = "cloudops.delete_bastionhost"

    def post(self, request, host_id: str, *args, **kwargs):
        payload = self._load_payload(request)
        cloud_id = self._get_cloud_id(request, payload)
        try:
            client = self._client()
            client.delete_host(host_id)
            client.clear_hosts_cache(cloud_id)
            log_operation(
                user=request.user,
                module="cloudops",
                action="delete_host",
                target=None,
                request=request,
                result="success",
            )
        except Exception as exc:
            log_operation(
                user=request.user,
                module="cloudops",
                action="delete_host",
                target=None,
                request=request,
                result="failed",
            )
            return self._handle_exception(exc)
        return self._json_ok({"message": "主机已删除。"})


class BastionUserInfoAPIView(BastionAPIViewBase):
    def get(self, request, account: str, *args, **kwargs):
        try:
            user_info = self._client().get_user_info(account)
        except Exception as exc:
            if isinstance(exc, JumpServerAPIError):
                err_text = str(exc)
                err_details = exc.details or ""
                if exc.status_code in {400, 404} or "/user/byAccount/" in err_text or "/user/byAccount/" in err_details:
                    return self._json_error("用户不存在", status=404)
            return self._handle_exception(exc)
        return self._json_ok({"user": user_info, "user_id": extract_user_id(user_info)})


class BastionCredentialPasswordAPIView(BastionAPIViewBase):
    permission_required = "cloudops.change_bastionhost"

    def post(self, request, *args, **kwargs):
        payload = self._load_payload(request)
        try:
            client = self._client()
            credential_id = str(payload.get("credentialId") or payload.get("credential_id") or "").strip()
            password = str(payload.get("password") or "").strip()
            if not password:
                raise JumpServerAPIError("新密码不能为空", status_code=400)

            resolved_host_id = ""
            if not credential_id:
                resolved_host_id = self._resolve_host_id(request, payload)
                credentials = client.get_credentials(host_id=resolved_host_id, force_refresh=True)
                credential_id = extract_first_credential_id(credentials)
                if not credential_id:
                    raise JumpServerAPIError("未查询到可修改的凭据ID，请先检查主机凭据", status_code=404)

            client.modify_credential_password(credential_id=credential_id, password=password)
            log_operation(
                user=request.user,
                module="cloudops",
                action="modify_credential_password",
                target=None,
                request=request,
                result="success",
            )
        except Exception as exc:
            log_operation(
                user=request.user,
                module="cloudops",
                action="modify_credential_password",
                target=None,
                request=request,
                result="failed",
            )
            return self._handle_exception(exc)

        return self._json_ok(
            {
                "message": "凭据密码修改成功。",
                "credential_id": credential_id,
                "host_id": resolved_host_id,
            }
        )


class BastionHostUserAuthAPIView(BastionAPIViewBase):
    permission_required = "cloudops.change_bastionhost"

    def post(self, request, *args, **kwargs):
        payload = self._load_payload(request)
        try:
            host_id = self._resolve_host_id(request, payload)
            user_id = str(payload.get("userId") or payload.get("user_id") or "").strip()
            if not user_id:
                raise JumpServerAPIError("缺少 user_id，无法添加授权", status_code=400)

            self._client().add_user_auth(host_id=host_id, user_id=user_id)
            log_operation(
                user=request.user,
                module="cloudops",
                action="add_user_auth",
                target=None,
                request=request,
                result="success",
            )
        except Exception as exc:
            log_operation(
                user=request.user,
                module="cloudops",
                action="add_user_auth",
                target=None,
                request=request,
                result="failed",
            )
            return self._handle_exception(exc)
        return self._json_ok({"message": "用户授权成功。", "host_id": host_id, "user_id": user_id})


class BastionPingAPIView(BastionAPIViewBase):
    def get(self, request, *args, **kwargs):
        try:
            data = self._client().ping()
        except Exception as exc:
            return self._handle_exception(exc)
        return self._json_ok({"data": data})


class SSHProxyRedirectView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "cloudops.view_bastionhost"

    def get(self, request, *args, **kwargs):
        client = get_jumpserver_client()
        try:
            redirect_url = client.get_oauth_login_url(
                user_id=request.GET.get("userId") or None,
                team_id=request.GET.get("teamId") or None,
                page=request.GET.get("page") or None,
                oneoff=str(request.GET.get("oneoff", "false")).strip().lower() in {"1", "true", "yes", "on"},
            )
        except JumpServerAPIError as exc:
            messages.error(request, f"免登录跳转失败：{exc}")
            return redirect("cloudops:bastion-list")
        except Exception:
            logger.exception("Failed to build JumpServer oauth redirect url")
            messages.error(request, "免登录跳转失败，请稍后再试。")
            return redirect("cloudops:bastion-list")
        return redirect(redirect_url)
