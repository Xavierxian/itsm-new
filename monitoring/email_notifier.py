from __future__ import annotations

import logging
import re
from datetime import datetime
from email.header import Header
from email.utils import formataddr
from html import escape
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from accounts.models import User

logger = logging.getLogger(__name__)


class AlertEmailNotifierError(RuntimeError):
    """Raised when alert email cannot be sent."""


class AlertEmailNotifier:
    _split_pattern = re.compile(r"[,\s;]+")
    _unknown_names = {"", "-", "unknown", "未知", "未设置", "n/a", "none"}
    _identifier_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def _parse_recipients(self, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            candidates = [part.strip() for part in self._split_pattern.split(value) if part.strip()]
        elif isinstance(value, (list, tuple, set)):
            candidates = [str(part or "").strip() for part in value if str(part or "").strip()]
        else:
            candidates = [str(value).strip()]

        seen: set[str] = set()
        valid: list[str] = []
        for candidate in candidates:
            lowered = candidate.lower()
            if lowered in seen:
                continue
            try:
                validate_email(candidate)
            except ValidationError:
                continue
            seen.add(lowered)
            valid.append(candidate)
        return valid

    def _safe_identifier(self, value: str, fallback: str) -> str:
        text = str(value or "").strip()
        if text and self._identifier_pattern.match(text):
            return text
        return fallback

    def _lookup_emails_by_name_from_dd_table(self, names: set[str]) -> dict[str, list[str]]:
        if not names:
            return {}

        table_name = self._safe_identifier(
            str(getattr(settings, "MONITORING_ALERT_USER_EMAIL_TABLE", "BS_DD_USER_BS") or "").strip(),
            "BS_DD_USER_BS",
        )
        name_column = self._safe_identifier(
            str(getattr(settings, "MONITORING_ALERT_USER_NAME_COLUMN", "name") or "").strip(),
            "name",
        )
        email_column = self._safe_identifier(
            str(getattr(settings, "MONITORING_ALERT_USER_EMAIL_COLUMN", "email") or "").strip(),
            "email",
        )

        sanitized_names = sorted({str(name or "").strip() for name in names if str(name or "").strip()})
        if not sanitized_names:
            return {}

        email_map: dict[str, list[str]] = {}
        try:
            chunk_size = 200
            with connection.cursor() as cursor:
                for start in range(0, len(sanitized_names), chunk_size):
                    chunk = sanitized_names[start : start + chunk_size]
                    placeholders = ", ".join(["%s"] * len(chunk))
                    sql = (
                        f"SELECT {name_column}, {email_column} "
                        f"FROM {table_name} "
                        f"WHERE {name_column} IN ({placeholders}) "
                        f"AND {email_column} IS NOT NULL AND {email_column} <> ''"
                    )
                    cursor.execute(sql, chunk)
                    for row in cursor.fetchall() or []:
                        if not row or len(row) < 2:
                            continue
                        name_text = str(row[0] or "").strip()
                        email_text = str(row[1] or "").strip()
                        if not name_text or not email_text:
                            continue
                        parsed = self._parse_recipients(email_text)
                        if not parsed:
                            continue
                        bucket = email_map.setdefault(name_text, [])
                        seen_local = {item.lower() for item in bucket}
                        for item in parsed:
                            lowered = item.lower()
                            if lowered in seen_local:
                                continue
                            bucket.append(item)
                            seen_local.add(lowered)
        except Exception as exc:
            logger.warning("Lookup recipient from DD table failed: %s", exc)
            return {}

        return email_map

    def _lookup_emails_by_name_from_user_table(self, names: set[str]) -> dict[str, list[str]]:
        email_map: dict[str, list[str]] = {}
        if not names:
            return email_map

        query = User.objects.filter(Q(full_name__in=names) | Q(username__in=names)).exclude(email__exact="").exclude(
            email__isnull=True
        )
        for user in query:
            email_text = str(user.email or "").strip()
            if not email_text:
                continue
            try:
                validate_email(email_text)
            except ValidationError:
                continue

            candidate_names = {str(user.full_name or "").strip(), str(user.username or "").strip()}
            for name in candidate_names:
                if not name or name not in names:
                    continue
                bucket = email_map.setdefault(name, [])
                lowered_set = {item.lower() for item in bucket}
                lowered = email_text.lower()
                if lowered in lowered_set:
                    continue
                bucket.append(email_text)
        return email_map

    def _merge_unique(self, target: list[str], source: list[str]) -> list[str]:
        seen = {item.lower() for item in target}
        for item in source:
            lowered = item.lower()
            if lowered in seen:
                continue
            target.append(item)
            seen.add(lowered)
        return target

    def _build_applicant_email_map(self, alerts: list[dict[str, Any]]) -> dict[str, list[str]]:
        applicant_email_map: dict[str, list[str]] = {}
        names = {
            str(item.get("applicant") or "").strip()
            for item in alerts
            if str(item.get("applicant") or "").strip().lower() not in self._unknown_names
        }

        # From alert payload first.
        for item in alerts:
            applicant = str(item.get("applicant") or "").strip()
            if not applicant:
                continue
            payload_emails = self._parse_recipients(item.get("applicant_email"))
            if payload_emails:
                applicant_email_map.setdefault(applicant, [])
                self._merge_unique(applicant_email_map[applicant], payload_emails)

        # DD table mapping.
        dd_map = self._lookup_emails_by_name_from_dd_table(names)
        for name, emails in dd_map.items():
            applicant_email_map.setdefault(name, [])
            self._merge_unique(applicant_email_map[name], emails)

        # Platform user mapping.
        user_map = self._lookup_emails_by_name_from_user_table(names)
        for name, emails in user_map.items():
            applicant_email_map.setdefault(name, [])
            self._merge_unique(applicant_email_map[name], emails)

        return applicant_email_map

    def _build_recipient_alert_map(
        self,
        alerts: list[dict[str, Any]],
        requested_recipients: Any,
        *,
        fallback_user_email: str = "",
    ) -> dict[str, list[dict[str, Any]]]:
        # If explicit recipients are provided (manual override), send full alerts to each,
        # but still send one email per recipient (not a single combined email).
        requested = self._parse_recipients(requested_recipients)
        if requested:
            return {email: list(alerts) for email in requested}

        configured = self._parse_recipients(getattr(settings, "MONITORING_ALERT_EMAIL_RECIPIENTS", ""))
        if configured:
            return {email: list(alerts) for email in configured}

        applicant_email_map = self._build_applicant_email_map(alerts)
        recipient_alert_map: dict[str, list[dict[str, Any]]] = {}
        unresolved_alerts: list[dict[str, Any]] = []

        for item in alerts:
            applicant = str(item.get("applicant") or "").strip()
            applicant_emails = applicant_email_map.get(applicant, []) if applicant else []
            if not applicant_emails:
                unresolved_alerts.append(item)
                continue
            for email in applicant_emails:
                recipient_alert_map.setdefault(email, [])
                recipient_alert_map[email].append(item)

        # If some alerts still cannot resolve owner email, fallback to current user.
        fallback_emails = self._parse_recipients(fallback_user_email)
        if unresolved_alerts and fallback_emails:
            fallback_target = fallback_emails[0]
            recipient_alert_map.setdefault(fallback_target, [])
            recipient_alert_map[fallback_target].extend(unresolved_alerts)

        return recipient_alert_map

    def _get_fixed_cc_recipients(self) -> list[str]:
        configured = getattr(settings, "MONITORING_ALERT_FIXED_CC", "")
        return self._parse_recipients(configured)

    def _format_from_address(self) -> str:
        from_email = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
        from_name = str(getattr(settings, "MONITORING_ALERT_FROM_NAME", "IT运维管理平台") or "").strip()
        if not from_email:
            from_email = str(getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
        if not from_email:
            raise AlertEmailNotifierError("未配置发件邮箱，请检查 FROM_EMAIL 或 SMTP_USERNAME。")
        if not from_name:
            return from_email
        return formataddr((str(Header(from_name, "utf-8")), from_email))

    def _build_subject(self, host_count: int, now_dt: datetime) -> str:
        return f"【IT运维管理平台】分区告警通知 - {host_count}台主机 ({now_dt:%Y-%m-%d %H:%M:%S})"

    def _resolve_greeting_name(self, alerts: list[dict[str, Any]]) -> str:
        names = []
        seen: set[str] = set()
        for item in alerts:
            applicant = str(item.get("applicant") or "").strip()
            if not applicant:
                continue
            lowered = applicant.lower()
            if lowered in self._unknown_names or lowered in seen:
                continue
            seen.add(lowered)
            names.append(applicant)
        if not names:
            return "您好"
        if len(names) == 1:
            return f"{names[0]}，你好"
        return "您好"

    def _build_text_body(self, alerts: list[dict[str, Any]], threshold: float, now_dt: datetime) -> str:
        total_alert_count = sum(len(item.get("alerts", [])) for item in alerts)
        greeting_name = self._resolve_greeting_name(alerts)
        lines = [
            f"{greeting_name}，你名下有{len(alerts)}台主机的磁盘使用率已达到限定阈值，信息如下：",
            "",
            "系统概览页分区告警通知",
            f"发送时间: {now_dt:%Y-%m-%d %H:%M:%S}",
            f"告警阈值: {threshold:.1f}%",
            f"告警主机数: {len(alerts)}",
            f"告警项总数: {total_alert_count}",
            "",
        ]

        for index, item in enumerate(alerts[:100], start=1):
            entries = item.get("alerts", []) if isinstance(item.get("alerts"), list) else []
            summary = "; ".join(
                f"{entry.get('metric_label') or entry.get('metric_key') or '分区'} "
                f"{float(entry.get('value') or 0):.1f}% (阈值 {float(entry.get('threshold') or threshold):.1f}%)"
                for entry in entries
            )
            lines.append(
                f"{index}. {item.get('ip') or item.get('instance') or '未知主机'} | "
                f"{item.get('os_type') or '未知'} | "
                f"{item.get('applicant') or '未知'} | "
                f"{item.get('department') or '未知'}"
            )
            lines.append(f"   告警详情: {summary or '无详细指标'}")

        if len(alerts) > 100:
            lines.append("")
            lines.append(f"其余 {len(alerts) - 100} 台主机告警请登录平台查看。")

        lines.append("")
        lines.append("请及时进行磁盘清理操作，删除不必要的日志文件、临时文件或过期数据，必要时可联系信息中心进行扩容，避免影响业务正常运行。")
        lines.append("此邮件由系统自动发送，请勿直接回复。")
        return "\n".join(lines)

    def _build_html_body(self, alerts: list[dict[str, Any]], threshold: float, now_dt: datetime) -> str:
        shown_alerts = alerts[:100]
        total_alert_count = sum(len(item.get("alerts", [])) for item in alerts)
        greeting_name = self._resolve_greeting_name(alerts)

        cards: list[str] = []
        for item in shown_alerts:
            entries = item.get("alerts", []) if isinstance(item.get("alerts"), list) else []
            tags = []
            for entry in entries:
                label = escape(str(entry.get("metric_label") or entry.get("metric_key") or "分区"))
                value = float(entry.get("value") or 0)
                entry_threshold = float(entry.get("threshold") or threshold)
                tags.append(
                    "<span class='tag' "
                    "style='display:inline-block;margin:0 8px 8px 0;padding:6px 10px;"
                    "background:#fff0f1;border:1px solid #ffd0d5;border-radius:999px;"
                    "font-size:13px;line-height:1.3;color:#b42334;white-space:normal;'>"
                    f"{label}: {value:.1f}% / 阈值 {entry_threshold:.1f}%"
                    "</span>"
                )

            cards.append(
                "<tr><td style='padding:0 0 12px;'>"
                "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
                "style='border:1px solid #dde3ee;border-radius:10px;background:#f9fbff;'>"
                "<tr><td class='card-cell' style='padding:14px 16px;'>"
                "<p class='host' style='margin:0 0 8px;font-size:20px;line-height:1.2;font-weight:700;color:#0f2f63;'>"
                f"{escape(str(item.get('ip') or item.get('instance') or '未知主机'))}"
                "</p>"
                "<p class='meta' style='margin:0 0 10px;font-size:14px;line-height:1.7;color:#4a5b73;'>"
                f"{escape(str(item.get('os_type') or '未知'))} | "
                f"{escape(str(item.get('applicant') or '未知'))} | "
                f"{escape(str(item.get('department') or '未知'))}"
                "</p>"
                "<div style='font-size:0;line-height:0;'>"
                + ("".join(tags) if tags else "<span style='font-size:13px;color:#6b7280;'>无告警详情</span>")
                + "</div>"
                "</td></tr></table>"
                "</td></tr>"
            )

        more_line = ""
        if len(alerts) > 100:
            more_line = (
                "<tr><td style='padding:4px 0 0;font-size:13px;line-height:1.6;color:#6b7280;'>"
                f"其余 {len(alerts) - 100} 台主机告警请登录平台查看。"
                "</td></tr>"
            )

        return (
            "<!doctype html>"
            "<html lang='zh-CN'>"
            "<head>"
            "<meta http-equiv='Content-Type' content='text/html; charset=UTF-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
            "<meta name='x-apple-disable-message-reformatting'>"
            "<title>分区告警通知</title>"
            "<style>"
            "body{margin:0;padding:0;background:#eef2f7;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}"
            "table{border-collapse:collapse;border-spacing:0;mso-table-lspace:0pt;mso-table-rspace:0pt;}"
            "@media only screen and (max-width:620px){"
            ".container{width:100%!important;}"
            ".outer-pad{padding-left:10px!important;padding-right:10px!important;}"
            ".head-cell{padding:18px 14px!important;}"
            ".title{font-size:22px!important;line-height:1.3!important;}"
            ".main-cell{padding:14px!important;}"
            ".summary-col{display:block!important;width:100%!important;}"
            ".summary-col td{display:block!important;width:100%!important;padding-bottom:8px!important;}"
            ".host{font-size:18px!important;}"
            ".meta{font-size:13px!important;line-height:1.6!important;}"
            ".card-cell{padding:12px!important;}"
            ".tag{display:block!important;margin-right:0!important;}"
            "}"
            "</style>"
            "</head>"
            "<body>"
            "<div style='display:none;max-height:0;overflow:hidden;opacity:0;'>"
            f"分区告警通知：共 {len(alerts)} 台主机触发阈值告警，请及时处理。"
            "</div>"
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>"
            "<tr><td align='center' class='outer-pad' style='padding:24px 12px;'>"
            "<table role='presentation' width='640' class='container' cellpadding='0' cellspacing='0' "
            "style='width:640px;max-width:640px;background:#ffffff;border:1px solid #dce3ee;border-radius:14px;overflow:hidden;'>"
            "<tr><td class='head-cell' style='padding:24px 22px;background:#154ea8;'>"
            "<p style='margin:0;font-size:13px;line-height:1.6;color:#d6e5ff;'>IT运维管理平台</p>"
            "<h1 class='title' style='margin:6px 0 0;font-size:26px;line-height:1.3;color:#ffffff;'>分区告警通知</h1>"
            "</td></tr>"
            "<tr><td class='main-cell' style='padding:20px 22px;'>"
            "<p style='margin:0 0 14px;font-size:15px;line-height:1.8;color:#1f2f46;'>"
            f"{escape(greeting_name)}，你名下有{len(alerts)}台主机的磁盘使用率已达到限定阈值，信息如下："
            "</p>"
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='margin:0 0 14px;'>"
            "<tr>"
            "<td class='summary-col' width='50%' valign='top' style='padding:0 8px 8px 0;'>"
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
            "style='background:#f3f7ff;border:1px solid #d9e5ff;border-radius:10px;'>"
            "<tr><td style='padding:10px 12px;font-size:13px;line-height:1.7;color:#35527a;'>"
            f"发送时间：{now_dt:%Y-%m-%d %H:%M:%S}<br>告警阈值：{threshold:.1f}%"
            "</td></tr></table></td>"
            "<td class='summary-col' width='50%' valign='top' style='padding:0 0 8px 8px;'>"
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
            "style='background:#fff5f6;border:1px solid #ffd9dc;border-radius:10px;'>"
            "<tr><td style='padding:10px 12px;font-size:13px;line-height:1.7;color:#7a2e39;'>"
            f"告警主机数：{len(alerts)} 台<br>告警项总数：{total_alert_count} 项"
            "</td></tr></table></td>"
            "</tr>"
            "</table>"
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>"
            + "".join(cards)
            + more_line
            + "</table>"
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='margin-top:8px;'>"
            "<tr><td style='padding-top:10px;border-top:1px solid #e4e7ef;'>"
            "<p style='margin:0 0 8px;font-size:12px;line-height:1.7;color:#6b7280;'>"
            "请及时进行磁盘清理操作，删除不必要的日志文件、临时文件或过期数据，必要时可联系信息中心进行扩容，避免影响业务正常运行。"
            "</p>"
            "<p style='margin:0;font-size:12px;line-height:1.7;color:#6b7280;'>"
            "此邮件由系统自动发送，请勿直接回复。"
            "</p>"
            "</td></tr></table>"
            "</td></tr>"
            "</table>"
            "</td></tr></table>"
            "</body></html>"
        )

    def send_partition_alert_email(
        self,
        alerts: list[dict[str, Any]],
        *,
        threshold: float,
        requested_recipients: Any = None,
        fallback_user_email: str = "",
    ) -> dict[str, Any]:
        if not alerts:
            raise AlertEmailNotifierError("当前没有达到阈值的分区告警，无需发送邮件。")

        if not str(getattr(settings, "EMAIL_HOST", "") or "").strip():
            raise AlertEmailNotifierError("未配置 SMTP_SERVER，无法发送邮件。")
        if not str(getattr(settings, "EMAIL_HOST_USER", "") or "").strip():
            raise AlertEmailNotifierError("未配置 SMTP_USERNAME，无法发送邮件。")
        if not str(getattr(settings, "EMAIL_HOST_PASSWORD", "") or "").strip():
            raise AlertEmailNotifierError("未配置 SMTP_PASSWORD，无法发送邮件。")

        recipient_alert_map = self._build_recipient_alert_map(
            alerts,
            requested_recipients,
            fallback_user_email=fallback_user_email,
        )
        if not recipient_alert_map:
            raise AlertEmailNotifierError("未解析到收件人邮箱，请先维护对接人邮箱。")

        now_dt = timezone.localtime()
        from_email = self._format_from_address()
        fixed_cc = self._get_fixed_cc_recipients()
        sent_recipients: list[str] = []
        failed_recipients: list[str] = []

        for recipient_email, recipient_alerts in recipient_alert_map.items():
            if not recipient_alerts:
                continue

            subject = self._build_subject(len(recipient_alerts), now_dt)
            text_body = self._build_text_body(recipient_alerts, threshold, now_dt)
            html_body = self._build_html_body(recipient_alerts, threshold, now_dt)

            try:
                cc_for_this_mail = [email for email in fixed_cc if email.lower() != recipient_email.lower()]
                message = EmailMultiAlternatives(
                    subject=subject,
                    body=text_body,
                    from_email=from_email,
                    to=[recipient_email],
                    cc=cc_for_this_mail,
                )
                message.attach_alternative(html_body, "text/html")
                delivered = message.send(fail_silently=False)
                if delivered > 0:
                    sent_recipients.append(recipient_email)
                else:
                    failed_recipients.append(recipient_email)
            except Exception:
                logger.exception("Send partition alert mail failed: %s", recipient_email)
                failed_recipients.append(recipient_email)

        if not sent_recipients:
            raise AlertEmailNotifierError("邮件发送失败，请稍后重试。")

        return {
            "sent_count": len(sent_recipients),
            "recipients": sent_recipients,
            "cc_recipients": fixed_cc,
            "failed_recipients": failed_recipients,
            "host_count": len(alerts),
            "alert_count": sum(len(item.get("alerts", [])) for item in alerts),
            "sent_at": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        }


alert_email_notifier = AlertEmailNotifier()
