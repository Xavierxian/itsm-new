from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any, Iterator
from urllib.parse import urlparse

import pymysql
import requests
from requests.adapters import HTTPAdapter
from django.conf import settings
from pymysql.cursors import DictCursor

from assets.models import VirtualMachine
from core.cache_helpers import cache_get, cache_set
from core.locks import cache_lock

logger = logging.getLogger(__name__)

IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
LINUX_PREFIXES = ("centos", "ubuntu", "xenenterprise", "linux", "debian", "rocky", "almalinux")
K8S_AI_SUMMARY_MAX_CHARS = 200
HOST_SNAPSHOT_CACHE_KEY = "monitoring:host:snapshot:v1"
HOST_SNAPSHOT_BUILD_LOCK_NAME = "monitoring_host_snapshot_build"


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    unit: str
    query: str


SNAPSHOT_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition("tcp_connections", "TCP连接", "", 'avg by(instance) (node_netstat_Tcp_CurrEstab)'),
    MetricDefinition("cpu_cores", "CPU核数", "core", 'count by(instance) (node_cpu_seconds_total{mode="idle"})'),
    MetricDefinition(
        "memory_gb",
        "内存总量",
        "GB",
        'avg by(instance) (node_memory_MemTotal_bytes{instance!~"xenenterprise.*"} / 1073741824 or numMem{instance=~"xenenterprise.*"} / 1024)',
    ),
    MetricDefinition(
        "disk_gb",
        "磁盘总量",
        "GB",
        'sum by(instance) (node_filesystem_size_bytes{fstype!~"tmpfs|squashfs|overlay",instance!~"xenenterprise.*"} / 1073741824 or numDisk{instance=~"xenenterprise.*"} / 1024)',
    ),
    MetricDefinition("uptime_days", "运行时长", "day", 'sum by(instance) ((time() - node_boot_time_seconds) / 86400)'),
    MetricDefinition("cpu_usage", "CPU使用率", "%", '100 * (1 - avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])))'),
    MetricDefinition(
        "memory_usage",
        "内存使用率",
        "%",
        '(sum by (instance) (100 * (1 - (node_memory_MemAvailable_bytes{instance!~"xenenterprise.*"} / on(instance) node_memory_MemTotal_bytes{instance!~"xenenterprise.*"})))) or (avg by (instance) (nodememPer{instance=~"xenenterprise.*"}))',
    ),
    MetricDefinition("root_usage", "ROOT分区使用率", "%", 'avg by (instance) (100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}))'),
    MetricDefinition("data_usage", "DATA分区使用率", "%", 'avg by (instance) (100 * (1 - node_filesystem_avail_bytes{mountpoint="/data"} / node_filesystem_size_bytes{mountpoint="/data"}))'),
    MetricDefinition("home_usage", "HOME分区使用率", "%", 'avg by (instance) (100 * (1 - node_filesystem_avail_bytes{mountpoint="/home"} / node_filesystem_size_bytes{mountpoint="/home"}))'),
    MetricDefinition(
        "xs_usage",
        "XS分区使用率",
        "%",
        'avg by(instance) (100 * (1 - node_filesystem_avail_bytes{device=~"/dev/mapper/XS.*"} / node_filesystem_size_bytes{device=~"/dev/mapper/XSLocalEXT.*"}))',
    ),
    MetricDefinition("io_usage", "磁盘IO使用率", "%", 'avg by (instance) (rate(node_disk_io_time_seconds_total{device!~"loop.*|ram.*"}[5m])) * 100'),
    MetricDefinition(
        "network_mbps",
        "网络流量",
        "MB/s",
        'sum by (instance) (rate(node_network_transmit_bytes_total{device!~"lo|docker.*|veth.*|cni.*"}[5m]) + rate(node_network_receive_bytes_total{device!~"lo|docker.*|veth.*|cni.*"}[5m])) / 1024 / 1024',
    ),
)

ALERT_METRIC_KEYS: tuple[str, ...] = ("root_usage", "data_usage", "home_usage")

TIME_RANGE_CONFIGS: dict[str, dict[str, int | str]] = {
    "5m": {"seconds": 300, "step": 15, "label": "最近5分钟"},
    "1h": {"seconds": 3600, "step": 60, "label": "过去1小时"},
    "3h": {"seconds": 10800, "step": 60, "label": "过去3小时"},
    "6h": {"seconds": 21600, "step": 60, "label": "过去6小时"},
    "24h": {"seconds": 86400, "step": 300, "label": "过去24小时"},
}

LINUX_TREND_QUERIES: tuple[MetricDefinition, ...] = (
    MetricDefinition("cpu", "CPU使用率", "%", '(1 - avg by(instance) (rate(node_cpu_seconds_total{mode="idle",instance="{instance}"}[1m]))) * 100'),
    MetricDefinition("memory", "内存使用率", "%", '(1 - (node_memory_MemAvailable_bytes{instance="{instance}"} / node_memory_MemTotal_bytes{instance="{instance}"})) * 100'),
    MetricDefinition("disk", "ROOT分区使用率", "%", '(1 - node_filesystem_avail_bytes{mountpoint="/",instance="{instance}"} / node_filesystem_size_bytes{mountpoint="/",instance="{instance}"}) * 100'),
)

WINDOWS_TREND_QUERIES: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "cpu",
        "CPU使用率",
        "%",
        '(1 - (sum(increase(windows_cpu_time_total{mode="idle",instance="{instance}"}[5m])) by(instance) / sum(increase(windows_cpu_time_total{instance="{instance}"}[5m])) by(instance))) * 100',
    ),
    MetricDefinition(
        "memory",
        "内存使用率",
        "%",
        '((windows_cs_physical_memory_bytes{instance="{instance}"} - windows_os_physical_memory_free_bytes{instance="{instance}"}) / windows_cs_physical_memory_bytes{instance="{instance}"} * 100)',
    ),
    MetricDefinition(
        "disk",
        "C盘使用率",
        "%",
        '(100 - (windows_logical_disk_free_bytes{volume="C:",instance="{instance}"} / windows_logical_disk_size_bytes{volume="C:",instance="{instance}"}) * 100)',
    ),
)


class MonitoringServiceError(RuntimeError):
    """Raised when monitoring data cannot be fetched from Prometheus."""


@lru_cache(maxsize=1)
def _prometheus_http_session() -> requests.Session:
    session = requests.Session()
    pool_size = max(8, int(getattr(settings, "MONITORING_HTTP_POOL_MAXSIZE", 32)))
    adapter = HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
        max_retries=0,
        pool_block=False,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class PrometheusClient:
    def __init__(self):
        self.base_url = str(getattr(settings, "MONITORING_PROMETHEUS_URL", "https://127.0.0.1:9090")).rstrip("/")
        self.timeout_seconds = int(getattr(settings, "MONITORING_REQUEST_TIMEOUT_SECONDS", 15))
        self.retries = int(getattr(settings, "MONITORING_REQUEST_RETRIES", 2))
        self.verify_tls = bool(getattr(settings, "MONITORING_VERIFY_TLS", True))
        self.allow_insecure_http = bool(getattr(settings, "ALLOW_INSECURE_UPSTREAM_HTTP", False))
        self.session = _prometheus_http_session()
        if urlparse(self.base_url).scheme.lower() != "https" and not self.allow_insecure_http:
            raise MonitoringServiceError(
                "Prometheus endpoint must use HTTPS. Set ALLOW_INSECURE_UPSTREAM_HTTP=true only for approved intranet exceptions."
            )

    def query(self, query: str) -> dict[str, Any]:
        return self._request("/api/v1/query", {"query": query})

    def query_range(self, query: str, *, start: int, end: int, step: int) -> dict[str, Any]:
        return self._request(
            "/api/v1/query_range",
            {
                "query": query,
                "start": start,
                "end": end,
                "step": step,
            },
        )

    def get_targets(self) -> dict[str, Any]:
        return self._request("/api/v1/targets", {})

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        last_error = ""

        for attempt in range(max(self.retries, 0) + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout_seconds,
                    verify=self.verify_tls,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") != "success":
                    error_text = str(payload.get("error") or "Prometheus API返回失败状态")
                    raise MonitoringServiceError(error_text)
                return payload
            except (requests.RequestException, ValueError, MonitoringServiceError) as exc:
                last_error = str(exc)
                if attempt >= self.retries:
                    break
                time.sleep(min(2**attempt, 3))

        raise MonitoringServiceError(f"无法从Prometheus获取数据: {last_error or '未知错误'}")


def _validate_https_endpoint(endpoint: str) -> None:
    scheme = urlparse(str(endpoint or "")).scheme.lower()
    if scheme == "https":
        return
    if bool(getattr(settings, "ALLOW_INSECURE_UPSTREAM_HTTP", False)):
        return
    raise MonitoringServiceError("Upstream endpoint must use HTTPS in current policy.")


def _host_snapshot_cache_ttl() -> int:
    try:
        ttl = int(getattr(settings, "MONITORING_HOST_SNAPSHOT_CACHE_SECONDS", 15))
    except (TypeError, ValueError):
        ttl = 15
    return max(0, min(ttl, 300))


def _is_valid_host_snapshot_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("hosts"), list)
        and isinstance(payload.get("metric_definitions"), list)
        and isinstance(payload.get("errors"), list)
    )


def _build_host_snapshot_uncached() -> dict[str, Any]:
    client = PrometheusClient()
    host_map: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for metric in SNAPSHOT_METRICS:
        try:
            payload = client.query(metric.query)
        except MonitoringServiceError as exc:
            logger.warning("Prometheus query failed for %s: %s", metric.key, exc)
            errors.append(f"{metric.label}: {exc}")
            continue

        for item in payload.get("data", {}).get("result", []):
            instance = str(item.get("metric", {}).get("instance") or "unknown").strip()
            value = _extract_single_value(item)
            if value is None:
                continue
            host = host_map.setdefault(instance, {"instance": instance, "metrics": {}})
            host["metrics"][metric.key] = value

    hosts = list(host_map.values())
    _enrich_host_metadata(hosts)
    _sort_hosts(hosts)

    return {
        "hosts": hosts,
        "metric_definitions": [
            {"key": metric.key, "label": metric.label, "unit": metric.unit}
            for metric in SNAPSHOT_METRICS
        ],
        "errors": errors,
    }


def fetch_host_snapshot(*, use_cache: bool = True, force_refresh: bool = False) -> dict[str, Any]:
    cache_ttl = _host_snapshot_cache_ttl()
    cache_enabled = use_cache and cache_ttl > 0

    if cache_enabled and not force_refresh:
        cached = cache_get(HOST_SNAPSHOT_CACHE_KEY)
        if _is_valid_host_snapshot_payload(cached):
            return cached

    if cache_enabled and not force_refresh:
        with cache_lock(HOST_SNAPSHOT_BUILD_LOCK_NAME, timeout=max(5, min(cache_ttl, 30))) as acquired:
            if acquired:
                cached = cache_get(HOST_SNAPSHOT_CACHE_KEY)
                if _is_valid_host_snapshot_payload(cached):
                    return cached
                payload = _build_host_snapshot_uncached()
                cache_set(HOST_SNAPSHOT_CACHE_KEY, payload, timeout=cache_ttl)
                return payload

            for _ in range(6):
                time.sleep(0.05)
                cached = cache_get(HOST_SNAPSHOT_CACHE_KEY)
                if _is_valid_host_snapshot_payload(cached):
                    return cached

    payload = _build_host_snapshot_uncached()
    if cache_enabled:
        cache_set(HOST_SNAPSHOT_CACHE_KEY, payload, timeout=cache_ttl)
    return payload


def build_host_alerts(hosts: list[dict[str, Any]], threshold: float = 90.0) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    for host in hosts:
        metrics = host.get("metrics", {})
        host_alerts: list[dict[str, Any]] = []

        for metric_key in ALERT_METRIC_KEYS:
            value = metrics.get(metric_key)
            if value is None:
                continue
            if value >= threshold:
                definition = _metric_definition_by_key(metric_key)
                host_alerts.append(
                    {
                        "metric_key": metric_key,
                        "metric_label": definition.label if definition else metric_key,
                        "value": value,
                        "threshold": threshold,
                    }
                )

        if not host_alerts:
            continue

        alerts.append(
            {
                "instance": host.get("instance", ""),
                "ip": host.get("ip", ""),
                "os_type": host.get("os_type", "未知"),
                "applicant": host.get("applicant", "未知"),
                "department": host.get("department", "未知"),
                "alerts": host_alerts,
            }
        )

    alerts.sort(key=lambda item: len(item.get("alerts", [])), reverse=True)
    return alerts


def fetch_host_trend(instance: str, range_key: str = "1h") -> dict[str, Any]:
    normalized_instance = (instance or "").strip()
    if not normalized_instance:
        raise MonitoringServiceError("主机实例为空，无法查询趋势数据")

    config = TIME_RANGE_CONFIGS.get(range_key) or TIME_RANGE_CONFIGS["1h"]
    end = int(time.time())
    start = end - int(config["seconds"])
    step = int(config["step"])

    is_linux = detect_linux_instance(normalized_instance)
    metric_queries = LINUX_TREND_QUERIES if is_linux else WINDOWS_TREND_QUERIES

    client = PrometheusClient()
    timestamps: list[str] = []
    series_map: dict[str, dict[str, Any]] = {}

    for metric in metric_queries:
        query = metric.query.format(instance=normalized_instance)
        try:
            payload = client.query_range(query, start=start, end=end, step=step)
        except MonitoringServiceError as exc:
            logger.warning("Prometheus range query failed for %s: %s", metric.key, exc)
            continue

        result = payload.get("data", {}).get("result", [])
        if not result:
            continue

        points = result[0].get("values", [])
        if not points:
            continue

        point_labels: list[str] = []
        point_values: list[float | None] = []
        for ts, value in points:
            point_labels.append(time.strftime("%H:%M", time.localtime(float(ts))))
            point_values.append(_safe_float(value))

        if not timestamps:
            timestamps = point_labels

        series_map[metric.key] = {
            "label": metric.label,
            "unit": metric.unit,
            "data": point_values,
        }

    if not series_map:
        raise MonitoringServiceError(f"未获取到主机 {normalized_instance} 的趋势数据")

    return {
        "instance": normalized_instance,
        "ip": extract_ip_from_instance(normalized_instance),
        "os_type": "Linux" if is_linux else "Windows",
        "range": range_key if range_key in TIME_RANGE_CONFIGS else "1h",
        "range_label": str(config["label"]),
        "timestamps": timestamps,
        "series": series_map,
    }


def fetch_prometheus_targets() -> list[dict[str, str]]:
    client = PrometheusClient()
    payload = client.get_targets()
    targets = payload.get("data", {}).get("activeTargets", [])

    parsed: list[dict[str, str]] = []
    for item in targets:
        parsed.append(
            {
                "endpoint": str(item.get("scrapeUrl") or ""),
                "health": str(item.get("health") or "unknown").lower(),
            }
        )
    return parsed


def fetch_k8s_summary() -> dict[str, Any]:
    latest = _k8s_query_one(
        """
        SELECT
            k8s_total_cpu,
            k8s_total_mem,
            node_number,
            namespace_number,
            pod_number,
            create_time
        FROM k8s_namespace_used
        ORDER BY create_time DESC
        LIMIT 1
        """
    )
    if not latest:
        raise MonitoringServiceError("K8S数据库暂无可用监控数据")

    namespaces = fetch_k8s_namespace_latest(hours=24)
    used_cpu_total = sum((_safe_float(row.get("k8s_namespace_cpu_num")) or 0.0) for row in namespaces)
    used_mem_total = sum((_safe_float(row.get("k8s_namespace_mem_num")) or 0.0) for row in namespaces)

    ranked = sorted(
        namespaces,
        key=lambda row: (
            _safe_float(row.get("k8s_namespace_cpu_per")) or 0.0,
            _safe_float(row.get("k8s_namespace_mem_per")) or 0.0,
        ),
        reverse=True,
    )[:8]

    normalized_latest = _normalize_row(latest)
    return {
        "cluster": normalized_latest,
        "used_cpu_total": used_cpu_total,
        "used_mem_total": used_mem_total,
        "top_namespaces": [_normalize_row(row) for row in ranked],
        "updated_at": normalized_latest.get("create_time"),
    }


def fetch_k8s_namespace_latest(hours: int = 24) -> list[dict[str, Any]]:
    interval_hours = _normalize_interval_hours(hours, max_hours=24 * 14)
    query = f"""
        SELECT
            k1.namespace,
            k1.k8s_namespace_cpu_num,
            k1.k8s_namespace_cpu_per,
            k1.k8s_namespace_mem_num,
            k1.k8s_namespace_mem_per,
            k1.namespace_pod,
            k1.node_number,
            k1.namespace_number,
            k1.pod_number,
            k1.create_time
        FROM k8s_namespace_used k1
        INNER JOIN (
            SELECT namespace, MAX(create_time) AS latest_time
            FROM k8s_namespace_used
            WHERE create_time >= DATE_SUB(NOW(), INTERVAL {interval_hours} HOUR)
            GROUP BY namespace
        ) k2 ON k1.namespace = k2.namespace AND k1.create_time = k2.latest_time
        ORDER BY k1.namespace
    """
    rows = _k8s_query_all(query)
    return [_normalize_row(row) for row in rows]


def fetch_k8s_nodes_latest(hours: int = 24) -> list[dict[str, Any]]:
    interval_hours = _normalize_interval_hours(hours, max_hours=24 * 14)
    query = f"""
        SELECT
            k1.node_ip,
            k1.k8s_total_nodecpu,
            k1.k8s_total_nodemem,
            k1.node_used_cpu_num,
            k1.node_used_cpu_per,
            k1.node_used_mem_num,
            k1.node_used_mem_per,
            k1.create_time
        FROM k8s_node_used k1
        INNER JOIN (
            SELECT node_ip, MAX(create_time) AS latest_time
            FROM k8s_node_used
            WHERE create_time >= DATE_SUB(NOW(), INTERVAL {interval_hours} HOUR)
            GROUP BY node_ip
        ) k2 ON k1.node_ip = k2.node_ip AND k1.create_time = k2.latest_time
        ORDER BY k1.node_ip
    """
    rows = _k8s_query_all(query)
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized = _normalize_row(row)

        # Some data sources do not persist *_per fields; derive them from used/total.
        cpu_per = _safe_float(normalized.get("node_used_cpu_per"))
        cpu_total = _safe_float(normalized.get("k8s_total_nodecpu"))
        cpu_used = _safe_float(normalized.get("node_used_cpu_num"))
        if cpu_per is None and cpu_total is not None and cpu_total > 0 and cpu_used is not None:
            normalized["node_used_cpu_per"] = round((cpu_used / cpu_total) * 100, 2)

        mem_per = _safe_float(normalized.get("node_used_mem_per"))
        mem_total = _safe_float(normalized.get("k8s_total_nodemem"))
        mem_used = _safe_float(normalized.get("node_used_mem_num"))
        if mem_per is None and mem_total is not None and mem_total > 0 and mem_used is not None:
            normalized["node_used_mem_per"] = round((mem_used / mem_total) * 100, 2)

        normalized_rows.append(normalized)

    return normalized_rows


def fetch_k8s_node_trend(node_ip: str, hours: int = 24) -> dict[str, Any]:
    node_text = str(node_ip or "").strip()
    if not node_text:
        raise MonitoringServiceError("node_ip 参数不能为空")

    interval_hours = _normalize_interval_hours(hours, max_hours=24 * 30)
    query = f"""
        SELECT
            node_ip,
            create_time,
            k8s_total_nodecpu AS total_cpu,
            node_used_cpu_num AS cpu_num,
            node_used_cpu_per AS cpu_per,
            k8s_total_nodemem AS total_mem,
            node_used_mem_num AS mem_num,
            node_used_mem_per AS mem_per
        FROM k8s_node_used
        WHERE node_ip = %s
          AND create_time >= DATE_SUB(NOW(), INTERVAL {interval_hours} HOUR)
        ORDER BY create_time
    """
    rows = _k8s_query_all(query, (node_text,))
    if not rows:
        return {
            "node_ip": node_text,
            "hours": interval_hours,
            "timestamps": [],
            "series": {
                "cpu_num": [],
                "cpu_per": [],
                "mem_num": [],
                "mem_per": [],
            },
        }

    labels: list[str] = []
    cpu_num_values: list[float | None] = []
    cpu_per_values: list[float | None] = []
    mem_num_values: list[float | None] = []
    mem_per_values: list[float | None] = []

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized = _normalize_row(row)
        created_at = row.get("create_time")
        if isinstance(created_at, datetime):
            labels.append(created_at.strftime("%m-%d %H:%M"))
        else:
            labels.append(str(created_at or "--"))

        cpu_num = _safe_float(normalized.get("cpu_num"))
        cpu_per = _safe_float(normalized.get("cpu_per"))
        total_cpu = _safe_float(normalized.get("total_cpu"))
        if cpu_per is None and cpu_num is not None and total_cpu is not None and total_cpu > 0:
            cpu_per = round((cpu_num / total_cpu) * 100, 2)
            normalized["cpu_per"] = cpu_per

        mem_num = _safe_float(normalized.get("mem_num"))
        mem_per = _safe_float(normalized.get("mem_per"))
        total_mem = _safe_float(normalized.get("total_mem"))
        if mem_per is None and mem_num is not None and total_mem is not None and total_mem > 0:
            mem_per = round((mem_num / total_mem) * 100, 2)
            normalized["mem_per"] = mem_per

        cpu_num_values.append(cpu_num)
        cpu_per_values.append(cpu_per)
        mem_num_values.append(mem_num)
        mem_per_values.append(mem_per)
        normalized_rows.append(normalized)

    return {
        "node_ip": node_text,
        "hours": interval_hours,
        "timestamps": labels,
        "series": {
            "cpu_num": cpu_num_values,
            "cpu_per": cpu_per_values,
            "mem_num": mem_num_values,
            "mem_per": mem_per_values,
        },
        "last_point": normalized_rows[-1],
    }


def fetch_k8s_namespace_trend(namespace: str, hours: int = 24) -> dict[str, Any]:
    namespace_text = str(namespace or "").strip()
    if not namespace_text:
        raise MonitoringServiceError("namespace 参数不能为空")

    interval_hours = _normalize_interval_hours(hours, max_hours=24 * 30)
    query = f"""
        SELECT
            namespace,
            create_time,
            k8s_namespace_cpu_num AS cpu_num,
            k8s_namespace_cpu_per AS cpu_per,
            k8s_namespace_mem_num AS mem_num,
            k8s_namespace_mem_per AS mem_per,
            namespace_pod
        FROM k8s_namespace_used
        WHERE namespace = %s
          AND create_time >= DATE_SUB(NOW(), INTERVAL {interval_hours} HOUR)
        ORDER BY create_time
    """
    rows = _k8s_query_all(query, (namespace_text,))
    if not rows:
        return {
            "namespace": namespace_text,
            "hours": interval_hours,
            "timestamps": [],
            "series": {
                "cpu_num": [],
                "cpu_per": [],
                "mem_num": [],
                "mem_per": [],
                "pod": [],
            },
        }

    labels: list[str] = []
    cpu_num_values: list[float | None] = []
    cpu_per_values: list[float | None] = []
    mem_num_values: list[float | None] = []
    mem_per_values: list[float | None] = []
    pod_values: list[float | None] = []

    for row in rows:
        created_at = row.get("create_time")
        if isinstance(created_at, datetime):
            labels.append(created_at.strftime("%m-%d %H:%M"))
        else:
            labels.append(str(created_at or "--"))
        cpu_num_values.append(_safe_float(row.get("cpu_num")))
        cpu_per_values.append(_safe_float(row.get("cpu_per")))
        mem_num_values.append(_safe_float(row.get("mem_num")))
        mem_per_values.append(_safe_float(row.get("mem_per")))
        pod_values.append(_safe_float(row.get("namespace_pod")))

    return {
        "namespace": namespace_text,
        "hours": interval_hours,
        "timestamps": labels,
        "series": {
            "cpu_num": cpu_num_values,
            "cpu_per": cpu_per_values,
            "mem_num": mem_num_values,
            "mem_per": mem_per_values,
            "pod": pod_values,
        },
        "last_point": _normalize_row(rows[-1]),
    }


def analyze_k8s_filtered_data(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    rows = _normalize_k8s_analysis_rows(body.get("rows"))
    if not rows:
        raise MonitoringServiceError("筛选后暂无可分析的命名空间数据")

    trend = _normalize_k8s_analysis_trend(body.get("trend"))
    selected_namespace = str(body.get("selected_namespace") or "").strip()
    keyword = str(body.get("keyword") or "").strip()
    sort_key = str(body.get("sort_key") or "").strip()
    sort_direction = str(body.get("sort_direction") or "desc").strip().lower()
    if sort_direction not in {"asc", "desc"}:
        sort_direction = "desc"

    rule_text = _build_k8s_rule_analysis(
        rows=rows,
        trend=trend,
        selected_namespace=selected_namespace,
        keyword=keyword,
        sort_key=sort_key,
        sort_direction=sort_direction,
    )
    result = {
        "source": "rule",
        "model": "",
        "text": rule_text,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scope": {
            "rows": len(rows),
            "selected_namespace": selected_namespace,
            "keyword": keyword,
            "sort_key": sort_key,
            "sort_direction": sort_direction,
        },
    }

    ai_config = _monitoring_ai_config()
    if not ai_config["enabled"]:
        return result

    try:
        llm_text = _call_k8s_analysis_llm(
            rows=rows,
            trend=trend,
            selected_namespace=selected_namespace,
            keyword=keyword,
            sort_key=sort_key,
            sort_direction=sort_direction,
            ai_config=ai_config,
        )
    except MonitoringServiceError as exc:
        logger.warning("K8S AI analysis failed, falling back to rule output: %s", exc)
        result["note"] = f"AI模型暂不可用，已回退到规则分析。原因: {exc}"
        return result

    if not llm_text:
        result["note"] = "AI模型返回内容为空，已回退到规则分析。"
        return result

    result["source"] = "llm"
    result["model"] = str(ai_config["model"])
    result["text"] = llm_text
    result["fallback_text"] = rule_text
    return result


def stream_k8s_namespace_analysis(namespace: str, hours: int = 24) -> Iterator[str]:
    namespace_text = str(namespace or "").strip()
    if not namespace_text:
        raise MonitoringServiceError("namespace 参数不能为空")

    interval_hours = _normalize_interval_hours(hours, max_hours=24 * 30)
    trend = fetch_k8s_namespace_trend(namespace_text, hours=interval_hours)
    timestamps = trend.get("timestamps") if isinstance(trend.get("timestamps"), list) else []
    if not timestamps:
        raise MonitoringServiceError(f"命名空间 {namespace_text} 在近 {interval_hours} 小时无趋势数据")

    stats = _build_k8s_namespace_trend_stats(trend)
    rule_text = _build_k8s_namespace_rule_analysis(
        namespace=namespace_text,
        hours=interval_hours,
        timestamps=timestamps,
        stats=stats,
    )
    short_rule_text = _complete_summary_with_scope(
        rule_text,
        scope_label="命名空间",
        scope_value=namespace_text,
        hours=interval_hours,
        max_chars=K8S_AI_SUMMARY_MAX_CHARS,
    )

    ai_config = _monitoring_ai_config()
    logger.info(
        "K8S namespace analysis requested namespace=%s hours=%s ai_enabled=%s ai_base_url=%s",
        namespace_text,
        interval_hours,
        bool(ai_config.get("enabled")),
        str(ai_config.get("base_url") or ""),
    )
    if ai_config["enabled"]:
        try:
            llm_parts: list[str] = []
            llm_stream = _stream_k8s_namespace_llm(
                namespace=namespace_text,
                hours=interval_hours,
                timestamps=timestamps,
                stats=stats,
                ai_config=ai_config,
            )
            try:
                for piece in llm_stream:
                    text = str(piece or "")
                    if not text:
                        continue
                    llm_parts.append(text)
            finally:
                try:
                    llm_stream.close()
                except Exception:
                    pass
            llm_text = _complete_summary_with_scope(
                "".join(llm_parts),
                scope_label="命名空间",
                scope_value=namespace_text,
                hours=interval_hours,
                max_chars=K8S_AI_SUMMARY_MAX_CHARS,
            )
            if llm_text:
                for chunk in _chunk_text(llm_text, 48):
                    yield chunk
                return
            raise MonitoringServiceError("AI接口返回空内容")
        except MonitoringServiceError as exc:
            logger.warning("K8S namespace streaming AI failed, fallback to rule analysis: %s", exc)
            fallback_text = _complete_summary_with_scope(
                f"AI分析回退：{exc}。{short_rule_text}",
                scope_label="命名空间",
                scope_value=namespace_text,
                hours=interval_hours,
                max_chars=K8S_AI_SUMMARY_MAX_CHARS,
            )
            for chunk in _chunk_text(fallback_text, 48):
                yield chunk
            return

    for chunk in _chunk_text(short_rule_text, 48):
        yield chunk


def stream_k8s_node_analysis(node_ip: str, hours: int = 24) -> Iterator[str]:
    node_text = str(node_ip or "").strip()
    if not node_text:
        raise MonitoringServiceError("node_ip 参数不能为空")

    interval_hours = _normalize_interval_hours(hours, max_hours=24 * 30)
    trend = fetch_k8s_node_trend(node_text, hours=interval_hours)
    timestamps = trend.get("timestamps") if isinstance(trend.get("timestamps"), list) else []
    if not timestamps:
        raise MonitoringServiceError(f"节点 {node_text} 在近 {interval_hours} 小时无趋势数据")

    stats = _build_k8s_node_trend_stats(trend)
    rule_text = _build_k8s_node_rule_analysis(
        node_ip=node_text,
        hours=interval_hours,
        timestamps=timestamps,
        stats=stats,
    )
    short_rule_text = _complete_summary_with_scope(
        rule_text,
        scope_label="节点",
        scope_value=node_text,
        hours=interval_hours,
        max_chars=K8S_AI_SUMMARY_MAX_CHARS,
    )

    ai_config = _monitoring_ai_config()
    logger.info(
        "K8S node analysis requested node_ip=%s hours=%s ai_enabled=%s ai_base_url=%s",
        node_text,
        interval_hours,
        bool(ai_config.get("enabled")),
        str(ai_config.get("base_url") or ""),
    )
    if ai_config["enabled"]:
        try:
            llm_parts: list[str] = []
            llm_stream = _stream_k8s_node_llm(
                node_ip=node_text,
                hours=interval_hours,
                timestamps=timestamps,
                stats=stats,
                ai_config=ai_config,
            )
            try:
                for piece in llm_stream:
                    text = str(piece or "")
                    if not text:
                        continue
                    llm_parts.append(text)
            finally:
                try:
                    llm_stream.close()
                except Exception:
                    pass
            llm_text = _complete_summary_with_scope(
                "".join(llm_parts),
                scope_label="节点",
                scope_value=node_text,
                hours=interval_hours,
                max_chars=K8S_AI_SUMMARY_MAX_CHARS,
            )
            if llm_text:
                for chunk in _chunk_text(llm_text, 48):
                    yield chunk
                return
            raise MonitoringServiceError("AI接口返回空内容")
        except MonitoringServiceError as exc:
            logger.warning("K8S node streaming AI failed, fallback to rule analysis: %s", exc)
            fallback_text = _complete_summary_with_scope(
                f"AI分析回退：{exc}。{short_rule_text}",
                scope_label="节点",
                scope_value=node_text,
                hours=interval_hours,
                max_chars=K8S_AI_SUMMARY_MAX_CHARS,
            )
            for chunk in _chunk_text(fallback_text, 48):
                yield chunk
            return

    for chunk in _chunk_text(short_rule_text, 48):
        yield chunk


def detect_linux_instance(instance: str) -> bool:
    text = (instance or "").strip().lower()
    return text.startswith(LINUX_PREFIXES)


def extract_ip_from_instance(instance: str) -> str:
    candidate_text = str(instance or "").strip()
    for ip_text in IPV4_PATTERN.findall(candidate_text):
        if _is_valid_ipv4(ip_text):
            return ip_text

    fallback = candidate_text.split("/", 1)[0]
    if ":" in fallback:
        fallback = fallback.split(":", 1)[0]
    return fallback


def _extract_single_value(result_item: dict[str, Any]) -> float | None:
    value_section = result_item.get("value")
    if not isinstance(value_section, list) or len(value_section) < 2:
        return None
    value = _safe_float(value_section[1])
    if value is None:
        return None
    return round(value, 2)


def _safe_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return numeric


def _is_valid_ipv4(text: str) -> bool:
    parts = text.split(".")
    if len(parts) != 4:
        return False
    try:
        values = [int(part) for part in parts]
    except ValueError:
        return False
    return all(0 <= value <= 255 for value in values)


def _metric_definition_by_key(metric_key: str) -> MetricDefinition | None:
    for metric in SNAPSHOT_METRICS:
        if metric.key == metric_key:
            return metric
    return None


def _enrich_host_metadata(hosts: list[dict[str, Any]]) -> None:
    owner_map = _load_owner_map()

    for host in hosts:
        instance = str(host.get("instance") or "")
        ip = extract_ip_from_instance(instance)
        owner = owner_map.get(ip, {"applicant": "未知", "department": "未知"})
        host["ip"] = ip
        host["os_type"] = "Linux" if detect_linux_instance(instance) else "Windows"
        host["applicant"] = owner.get("applicant") or "未知"
        host["department"] = owner.get("department") or "未知"


def _load_owner_map() -> dict[str, dict[str, str]]:
    owner_map: dict[str, dict[str, str]] = {}
    queryset = VirtualMachine.objects.exclude(vm_ip__isnull=True).exclude(vm_ip__exact="")

    for vm_ip, applicant, department, in_use in queryset.values_list("vm_ip", "applicant", "department", "in_use"):
        if not _is_active_in_use(in_use):
            continue
        ip = str(vm_ip or "").strip()
        if not ip or ip in owner_map:
            continue
        owner_map[ip] = {
            "applicant": str(applicant or "").strip() or "未知",
            "department": str(department or "").strip() or "未知",
        }

    return owner_map


def _sort_hosts(hosts: list[dict[str, Any]]) -> None:
    hosts.sort(key=lambda item: (str(item.get("ip") or ""), str(item.get("instance") or "")))


def _is_active_in_use(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"是", "y", "yes", "1", "true", "在用", "启用", "enabled"}


def _normalize_interval_hours(hours: int, *, max_hours: int) -> int:
    try:
        value = int(hours)
    except (TypeError, ValueError):
        value = 24
    return max(1, min(value, max_hours))


def _k8s_db_config() -> dict[str, Any]:
    raw = getattr(settings, "MONITORING_K8S_DB", {}) or {}
    config = {
        "host": str(raw.get("HOST") or "").strip(),
        "port": int(raw.get("PORT") or 3306),
        "user": str(raw.get("USER") or "").strip(),
        "password": str(raw.get("PASSWORD") or ""),
        "database": str(raw.get("NAME") or "").strip(),
        "charset": str(raw.get("CHARSET") or "utf8mb4"),
        "connect_timeout": int(raw.get("CONNECT_TIMEOUT") or 6),
        "read_timeout": int(raw.get("READ_TIMEOUT") or 20),
        "write_timeout": int(raw.get("WRITE_TIMEOUT") or 20),
    }
    missing = [key for key in ("host", "user", "database") if not config[key]]
    if missing:
        raise MonitoringServiceError(f"K8S监控数据库配置缺失: {', '.join(missing)}")
    return config


def _k8s_query_all(query: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    config = _k8s_db_config()
    connection = None
    try:
        connection = pymysql.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
            charset=config["charset"],
            connect_timeout=config["connect_timeout"],
            read_timeout=config["read_timeout"],
            write_timeout=config["write_timeout"],
            cursorclass=DictCursor,
        )
        with connection.cursor() as cursor:
            cursor.execute(query, params or ())
            return list(cursor.fetchall() or [])
    except pymysql.MySQLError as exc:
        raise MonitoringServiceError(f"K8S数据库查询失败: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def _k8s_query_one(query: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    rows = _k8s_query_all(query, params=params)
    return rows[0] if rows else None


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            normalized[key] = float(value)
        elif isinstance(value, datetime):
            normalized[key] = value.strftime("%Y-%m-%d %H:%M:%S")
        else:
            normalized[key] = value
    return normalized


def _monitoring_ai_config() -> dict[str, Any]:
    raw = getattr(settings, "MONITORING_AI", {}) or {}
    try:
        timeout = int(raw.get("TIMEOUT_SECONDS") or 20)
    except (TypeError, ValueError):
        timeout = 20
    try:
        max_rows = int(raw.get("MAX_ROWS") or 120)
    except (TypeError, ValueError):
        max_rows = 120
    try:
        temperature = float(raw.get("TEMPERATURE") or 0.55)
    except (TypeError, ValueError):
        temperature = 0.55
    try:
        top_p = float(raw.get("TOP_P") or 0.95)
    except (TypeError, ValueError):
        top_p = 0.95
    return {
        "enabled": bool(raw.get("ENABLED")),
        "base_url": str(raw.get("BASE_URL") or "").strip(),
        "api_key": str(raw.get("API_KEY") or "").strip(),
        "model": str(raw.get("MODEL") or "").strip(),
        "timeout_seconds": max(5, min(timeout, 120)),
        "max_rows": max(10, min(max_rows, 300)),
        "temperature": max(0.0, min(temperature, 1.5)),
        "top_p": max(0.1, min(top_p, 1.0)),
    }


def _normalize_k8s_analysis_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value[:300]:
        if not isinstance(item, dict):
            continue
        namespace = str(item.get("namespace") or "").strip()
        if not namespace:
            continue
        rows.append(
            {
                "namespace": namespace,
                "cpu_num": _safe_float(item.get("k8s_namespace_cpu_num")),
                "cpu_per": _safe_float(item.get("k8s_namespace_cpu_per")),
                "mem_num": _safe_float(item.get("k8s_namespace_mem_num")),
                "mem_per": _safe_float(item.get("k8s_namespace_mem_per")),
                "pod": _safe_float(item.get("namespace_pod")),
                "create_time": str(item.get("create_time") or ""),
            }
        )
    return rows


def _normalize_k8s_analysis_trend(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "namespace": "",
            "hours": 24,
            "timestamps": [],
            "cpu_per": [],
            "mem_per": [],
            "pod": [],
        }
    series = value.get("series") if isinstance(value.get("series"), dict) else {}
    timestamps = value.get("timestamps") if isinstance(value.get("timestamps"), list) else []
    hours = _normalize_interval_hours(value.get("hours"), max_hours=24 * 30)
    return {
        "namespace": str(value.get("namespace") or "").strip(),
        "hours": hours,
        "timestamps": [str(item) for item in timestamps[:500]],
        "cpu_per": _normalize_numeric_series(series.get("cpu_per")),
        "mem_per": _normalize_numeric_series(series.get("mem_per")),
        "pod": _normalize_numeric_series(series.get("pod")),
    }


def _normalize_numeric_series(value: Any) -> list[float | None]:
    if not isinstance(value, list):
        return []
    return [_safe_float(item) for item in value[:500]]


def _build_k8s_rule_analysis(
    *,
    rows: list[dict[str, Any]],
    trend: dict[str, Any],
    selected_namespace: str,
    keyword: str,
    sort_key: str,
    sort_direction: str,
) -> str:
    total = len(rows)
    cpu_values = [value for value in (row.get("cpu_per") for row in rows) if value is not None]
    mem_values = [value for value in (row.get("mem_per") for row in rows) if value is not None]
    pod_values = [value for value in (row.get("pod") for row in rows) if value is not None]

    avg_cpu = sum(cpu_values) / len(cpu_values) if cpu_values else 0.0
    avg_mem = sum(mem_values) / len(mem_values) if mem_values else 0.0
    avg_pod = sum(pod_values) / len(pod_values) if pod_values else 0.0

    hot_rows = [
        row
        for row in rows
        if (row.get("cpu_per") is not None and row.get("cpu_per", 0) >= 80)
        or (row.get("mem_per") is not None and row.get("mem_per", 0) >= 80)
    ]

    top_cpu = _top_k8s_rows(rows, key="cpu_per", limit=3)
    top_mem = _top_k8s_rows(rows, key="mem_per", limit=3)
    top_pod = _top_k8s_rows(rows, key="pod", limit=3)

    lines: list[str] = []
    if keyword:
        lines.append(f"筛选关键词“{keyword}”下共 {total} 个命名空间，当前排序为 {sort_key or '默认'}（{sort_direction}）。")
    else:
        lines.append(f"当前筛选范围包含 {total} 个命名空间，排序为 {sort_key or '默认'}（{sort_direction}）。")
    lines.append(f"整体均值: CPU {avg_cpu:.2f}% / MEM {avg_mem:.2f}% / POD {avg_pod:.1f}。")

    if hot_rows:
        lines.append(f"高风险命名空间 {len(hot_rows)} 个（CPU 或 MEM >= 80%），建议优先排查资源配额和异常副本。")
    else:
        lines.append("未发现 CPU 或 MEM 超过 80% 的命名空间，整体负载处于可控范围。")

    lines.append("CPU Top3: " + _format_top_rows(top_cpu, "cpu_per", "%"))
    lines.append("MEM Top3: " + _format_top_rows(top_mem, "mem_per", "%"))
    lines.append("POD Top3: " + _format_top_rows(top_pod, "pod", ""))

    trend_line = _build_k8s_trend_line(trend, selected_namespace)
    if trend_line:
        lines.append(trend_line)

    lines.append("建议: 关注持续抬升的命名空间，结合 HPA/配额/限流策略做针对性优化。")
    return "\n".join(lines)


def _top_k8s_rows(rows: list[dict[str, Any]], *, key: str, limit: int) -> list[dict[str, Any]]:
    valid = [row for row in rows if row.get(key) is not None]
    valid.sort(key=lambda item: item.get(key) or 0.0, reverse=True)
    return valid[: max(1, limit)]


def _format_top_rows(rows: list[dict[str, Any]], key: str, unit: str) -> str:
    if not rows:
        return "无数据"
    parts: list[str] = []
    for row in rows:
        namespace = str(row.get("namespace") or "--")
        value = row.get(key)
        if value is None:
            parts.append(f"{namespace}(N/A)")
            continue
        if unit:
            parts.append(f"{namespace}({value:.2f}{unit})")
        else:
            parts.append(f"{namespace}({value:.0f})")
    return "，".join(parts)


def _build_k8s_trend_line(trend: dict[str, Any], selected_namespace: str) -> str:
    namespace = selected_namespace or str(trend.get("namespace") or "").strip()
    cpu_series = [value for value in trend.get("cpu_per", []) if value is not None]
    mem_series = [value for value in trend.get("mem_per", []) if value is not None]
    if not namespace or (not cpu_series and not mem_series):
        return ""

    parts: list[str] = [f"趋势观察（{namespace}，近 {trend.get('hours') or 24} 小时）:"]
    if cpu_series:
        cpu_start = cpu_series[0]
        cpu_end = cpu_series[-1]
        cpu_delta = cpu_end - cpu_start
        cpu_peak = max(cpu_series)
        parts.append(f"CPU {cpu_start:.2f}%→{cpu_end:.2f}% ({cpu_delta:+.2f}%)，峰值 {cpu_peak:.2f}%")
    if mem_series:
        mem_start = mem_series[0]
        mem_end = mem_series[-1]
        mem_delta = mem_end - mem_start
        mem_peak = max(mem_series)
        parts.append(f"MEM {mem_start:.2f}%→{mem_end:.2f}% ({mem_delta:+.2f}%)，峰值 {mem_peak:.2f}%")
    return "；".join(parts)


def _call_k8s_analysis_llm(
    *,
    rows: list[dict[str, Any]],
    trend: dict[str, Any],
    selected_namespace: str,
    keyword: str,
    sort_key: str,
    sort_direction: str,
    ai_config: dict[str, Any],
) -> str:
    if not ai_config.get("base_url"):
        raise MonitoringServiceError("MONITORING_AI_BASE_URL 未配置")
    if not ai_config.get("api_key"):
        raise MonitoringServiceError("MONITORING_AI_API_KEY 未配置")
    if not ai_config.get("model"):
        raise MonitoringServiceError("MONITORING_AI_MODEL 未配置")

    rows_for_ai = rows[: int(ai_config["max_rows"])]
    top_cpu = _top_k8s_rows(rows_for_ai, key="cpu_per", limit=5)
    top_mem = _top_k8s_rows(rows_for_ai, key="mem_per", limit=5)
    top_pod = _top_k8s_rows(rows_for_ai, key="pod", limit=5)

    cpu_values = [value for value in (row.get("cpu_per") for row in rows_for_ai) if value is not None]
    mem_values = [value for value in (row.get("mem_per") for row in rows_for_ai) if value is not None]
    pod_values = [value for value in (row.get("pod") for row in rows_for_ai) if value is not None]
    compact_payload = {
        "scope": {
            "selected_namespace": selected_namespace,
            "keyword": keyword,
            "sort_key": sort_key,
            "sort_direction": sort_direction,
            "namespace_count": len(rows_for_ai),
        },
        "summary": {
            "avg_cpu_per": round(sum(cpu_values) / len(cpu_values), 3) if cpu_values else 0.0,
            "avg_mem_per": round(sum(mem_values) / len(mem_values), 3) if mem_values else 0.0,
            "avg_pod": round(sum(pod_values) / len(pod_values), 3) if pod_values else 0.0,
            "cpu_over_80": sum(1 for value in cpu_values if value >= 80),
            "mem_over_80": sum(1 for value in mem_values if value >= 80),
        },
        "top_cpu": top_cpu,
        "top_mem": top_mem,
        "top_pod": top_pod,
        "trend": {
            "namespace": trend.get("namespace"),
            "hours": trend.get("hours"),
            "timestamps": trend.get("timestamps", [])[-36:],
            "cpu_per": trend.get("cpu_per", [])[-36:],
            "mem_per": trend.get("mem_per", [])[-36:],
            "pod": trend.get("pod", [])[-36:],
        },
    }

    system_prompt = (
        "你是企业运维监控助手。请基于给定K8S筛选数据输出简洁专业的分析，"
        "聚焦负载风险、趋势变化和可执行建议，不要虚构数据。"
    )
    user_prompt = (
        "请按照下面格式输出：\n"
        "1) 总体结论（1-2句）\n"
        "2) 关键风险（最多3条）\n"
        "3) 优化建议（最多3条）\n\n"
        "监控数据JSON:\n"
        + json.dumps(compact_payload, ensure_ascii=False)
    )

    endpoint = str(ai_config["base_url"]).rstrip("/") + "/chat/completions"
    _validate_https_endpoint(endpoint)
    request_body = {
        "model": ai_config["model"],
        "temperature": ai_config["temperature"],
        "top_p": ai_config["top_p"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {ai_config['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            endpoint,
            json=request_body,
            headers=headers,
            timeout=int(ai_config["timeout_seconds"]),
            verify=bool(ai_config.get("verify_tls", True)),
        )
    except requests.RequestException as exc:
        raise MonitoringServiceError(f"AI请求失败: {exc}") from exc

    if response.status_code >= 400:
        error_text = response.text[:400]
        raise MonitoringServiceError(f"AI接口返回异常 HTTP {response.status_code}: {error_text}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise MonitoringServiceError("AI接口返回非JSON数据") from exc

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise MonitoringServiceError("AI接口未返回可用结果")

    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, list):
        content = "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        )

    text = str(content or "").strip()
    if not text:
        raise MonitoringServiceError("AI接口返回内容为空")
    return text[:3000]


def _build_k8s_namespace_trend_stats(trend: dict[str, Any]) -> dict[str, dict[str, Any]]:
    series = trend.get("series") if isinstance(trend.get("series"), dict) else {}
    return {
        "cpu_num": _build_series_stats(series.get("cpu_num")),
        "cpu_per": _build_series_stats(series.get("cpu_per")),
        "mem_num": _build_series_stats(series.get("mem_num")),
        "mem_per": _build_series_stats(series.get("mem_per")),
        "pod": _build_series_stats(series.get("pod")),
    }


def _build_k8s_node_trend_stats(trend: dict[str, Any]) -> dict[str, dict[str, Any]]:
    series = trend.get("series") if isinstance(trend.get("series"), dict) else {}
    return {
        "cpu_num": _build_series_stats(series.get("cpu_num")),
        "cpu_per": _build_series_stats(series.get("cpu_per")),
        "mem_num": _build_series_stats(series.get("mem_num")),
        "mem_per": _build_series_stats(series.get("mem_per")),
    }


def _build_series_stats(values: Any) -> dict[str, Any]:
    if not isinstance(values, list):
        return {"count": 0}
    valid: list[tuple[int, float]] = []
    for idx, raw in enumerate(values):
        num = _safe_float(raw)
        if num is None:
            continue
        valid.append((idx, num))
    if not valid:
        return {"count": 0}

    first_idx, first_val = valid[0]
    last_idx, last_val = valid[-1]
    delta = last_val - first_val
    delta_ratio = None if abs(first_val) < 1e-9 else (delta / first_val) * 100
    min_idx, min_val = min(valid, key=lambda item: item[1])
    max_idx, max_val = max(valid, key=lambda item: item[1])
    avg_val = sum(item[1] for item in valid) / len(valid)

    return {
        "count": len(valid),
        "first_index": first_idx,
        "last_index": last_idx,
        "start": first_val,
        "end": last_val,
        "delta": delta,
        "delta_ratio": delta_ratio,
        "min": min_val,
        "min_index": min_idx,
        "max": max_val,
        "max_index": max_idx,
        "avg": avg_val,
    }


def _build_k8s_namespace_rule_analysis(
    *,
    namespace: str,
    hours: int,
    timestamps: list[str],
    stats: dict[str, dict[str, Any]],
) -> str:
    lines: list[str] = [
        f"命名空间 {namespace} 在近 {hours} 小时内共有 {len(timestamps)} 个监控时间点。",
        _format_series_analysis_line("CPU核", stats.get("cpu_num", {}), timestamps, unit="核", decimals=2, delta_unit="核"),
        _format_series_analysis_line("内存用量", stats.get("mem_num", {}), timestamps, unit="GB", decimals=2, delta_unit="GB"),
        _format_series_analysis_line("POD数量", stats.get("pod", {}), timestamps, unit="", decimals=0, delta_unit="个"),
    ]
    lines.append("结论建议: 重点跟踪CPU核、内存GB与POD变化，若持续上升请提前做容量与副本策略调整。")
    return "\n".join([line for line in lines if line])


def _build_k8s_node_rule_analysis(
    *,
    node_ip: str,
    hours: int,
    timestamps: list[str],
    stats: dict[str, dict[str, Any]],
) -> str:
    lines: list[str] = [
        f"节点 {node_ip} 在近 {hours} 小时内共有 {len(timestamps)} 个监控时间点。",
        _format_series_analysis_line("CPU已用", stats.get("cpu_num", {}), timestamps, unit="核", decimals=2, delta_unit="核"),
        _format_series_analysis_line("CPU使用率", stats.get("cpu_per", {}), timestamps, unit="%", decimals=2, delta_unit="个百分点"),
        _format_series_analysis_line("内存已用", stats.get("mem_num", {}), timestamps, unit="GB", decimals=2, delta_unit="GB"),
        _format_series_analysis_line("内存使用率", stats.get("mem_per", {}), timestamps, unit="%", decimals=2, delta_unit="个百分点"),
    ]

    cpu_peak = stats.get("cpu_per", {}).get("max")
    mem_peak = stats.get("mem_per", {}).get("max")
    high_risk = (isinstance(cpu_peak, (int, float)) and cpu_peak >= 80) or (
        isinstance(mem_peak, (int, float)) and mem_peak >= 80
    )
    if high_risk:
        lines.append("结论建议: 近时段出现 CPU 或内存高位占用，建议优先排查异常负载并评估扩容。")
    else:
        lines.append("结论建议: CPU与内存整体波动可控，建议持续观察峰值时段并预留容量缓冲。")
    return "\n".join([line for line in lines if line])


def _format_series_analysis_line(
    name: str,
    stat: dict[str, Any],
    timestamps: list[str],
    *,
    unit: str,
    decimals: int,
    delta_unit: str,
) -> str:
    if not stat or not stat.get("count"):
        return f"{name}: 当前时间范围内无可用数据。"

    start = float(stat.get("start") or 0.0)
    end = float(stat.get("end") or 0.0)
    delta = float(stat.get("delta") or 0.0)
    delta_ratio = stat.get("delta_ratio")
    max_val = float(stat.get("max") or 0.0)
    min_val = float(stat.get("min") or 0.0)
    avg_val = float(stat.get("avg") or 0.0)
    max_time = _timestamp_at(timestamps, stat.get("max_index"))
    min_time = _timestamp_at(timestamps, stat.get("min_index"))

    if delta > 0:
        direction = "增大"
    elif delta < 0:
        direction = "减小"
    else:
        direction = "基本持平"

    start_text = _format_metric_value(start, decimals, unit)
    end_text = _format_metric_value(end, decimals, unit)
    delta_text = _format_metric_delta(delta, decimals, delta_unit)
    ratio_text = ""
    if isinstance(delta_ratio, (int, float)):
        ratio_text = f"，相对变化 {delta_ratio:+.2f}%"
    avg_text = _format_metric_value(avg_val, decimals, unit)
    max_text = _format_metric_value(max_val, decimals, unit)
    min_text = _format_metric_value(min_val, decimals, unit)

    return (
        f"{name}: {start_text} → {end_text}，整体{direction} {delta_text}{ratio_text}；"
        f"均值 {avg_text}，峰值 {max_text}（{max_time}），谷值 {min_text}（{min_time}）。"
    )


def _format_metric_value(value: float, decimals: int, unit: str) -> str:
    if decimals <= 0:
        return f"{value:.0f}{unit}"
    return f"{value:.{decimals}f}{unit}"


def _format_metric_delta(value: float, decimals: int, unit: str) -> str:
    abs_val = abs(value)
    if decimals <= 0:
        return f"{abs_val:.0f}{unit}"
    return f"{abs_val:.{decimals}f}{unit}"


def _timestamp_at(timestamps: list[str], index: Any) -> str:
    if not isinstance(index, int):
        return "--"
    if index < 0 or index >= len(timestamps):
        return "--"
    return str(timestamps[index] or "--")


def _stream_k8s_namespace_llm(
    *,
    namespace: str,
    hours: int,
    timestamps: list[str],
    stats: dict[str, dict[str, Any]],
    ai_config: dict[str, Any],
) -> Iterator[str]:
    if not ai_config.get("base_url"):
        raise MonitoringServiceError("MONITORING_AI_BASE_URL 未配置")
    if not ai_config.get("api_key"):
        raise MonitoringServiceError("MONITORING_AI_API_KEY 未配置")
    if not ai_config.get("model"):
        raise MonitoringServiceError("MONITORING_AI_MODEL 未配置")

    prompt_payload = {
        "namespace": namespace,
        "hours": hours,
        "all_point_count": len(timestamps),
        "window_start": timestamps[0] if timestamps else "--",
        "window_end": timestamps[-1] if timestamps else "--",
        "stats_from_all_points": stats,
    }

    system_prompt = (
        "你是K8S资源监控分析助手。输出必须是纯文本单段总结，不超过200个中文字符。"
        "仅围绕CPU核、内存GB、POD数量三项，说明增减方向与关键变化量；禁止Markdown和分点。"
        "必须输出完整句，不允许冒号结尾、字段列到一半、半句话被截断。"
        "开头必须明确写出命名空间名称和统计时间范围（近X小时）。"
    )
    user_prompt = (
        "请基于以下统计生成一段精炼总结（<=200字）。"
        "要说明整体趋势，并给出CPU核、内存GB、POD数量的变化方向与主要变化量。"
        f"首句必须包含“命名空间{namespace}在近{hours}小时内”。"
        "若信息过多，请主动压缩措辞，不要省略成未完成字段。"
        "不要出现“总体判断/风险建议”标题，不要换行，不要使用列表符号。\n\n"
        "输入数据(JSON，已基于当前命名空间与所选时间范围全部时间节点统计):\n"
        + json.dumps(prompt_payload, ensure_ascii=False)
    )

    endpoint = str(ai_config["base_url"]).rstrip("/") + "/chat/completions"
    _validate_https_endpoint(endpoint)
    request_body = {
        "model": ai_config["model"],
        "temperature": ai_config["temperature"],
        "top_p": ai_config["top_p"],
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {ai_config['api_key']}",
        "Content-Type": "application/json",
    }

    response = None
    try:
        response = requests.post(
            endpoint,
            json=request_body,
            headers=headers,
            timeout=int(ai_config["timeout_seconds"]),
            verify=bool(ai_config.get("verify_tls", True)),
            stream=True,
        )
    except requests.RequestException as exc:
        raise MonitoringServiceError(f"AI请求失败: {exc}") from exc

    if response.status_code >= 400:
        error_text = response.text[:400]
        raise MonitoringServiceError(f"AI接口返回异常 HTTP {response.status_code}: {error_text}")

    content_type = str(response.headers.get("Content-Type") or "").lower()
    try:
        if "text/event-stream" in content_type:
            yielded = False
            for raw_line in response.iter_lines(decode_unicode=False):
                if isinstance(raw_line, (bytes, bytearray)):
                    line = raw_line.decode("utf-8", errors="replace").strip()
                else:
                    line = str(raw_line or "").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if not data_text:
                    continue
                if data_text == "[DONE]":
                    break
                try:
                    payload = json.loads(data_text)
                except ValueError:
                    continue
                delta_text = _extract_stream_delta_text(payload)
                if delta_text:
                    yielded = True
                    yield delta_text
            if yielded:
                return
            raise MonitoringServiceError("AI流式响应为空")

        try:
            payload = response.json()
        except ValueError as exc:
            raise MonitoringServiceError("AI接口返回非JSON数据") from exc
        text = _extract_nonstream_content(payload)
        if not text:
            raise MonitoringServiceError("AI接口返回内容为空")
        yield text
    finally:
        if response is not None:
            response.close()


def _stream_k8s_node_llm(
    *,
    node_ip: str,
    hours: int,
    timestamps: list[str],
    stats: dict[str, dict[str, Any]],
    ai_config: dict[str, Any],
) -> Iterator[str]:
    if not ai_config.get("base_url"):
        raise MonitoringServiceError("MONITORING_AI_BASE_URL 未配置")
    if not ai_config.get("api_key"):
        raise MonitoringServiceError("MONITORING_AI_API_KEY 未配置")
    if not ai_config.get("model"):
        raise MonitoringServiceError("MONITORING_AI_MODEL 未配置")

    prompt_payload = {
        "node_ip": node_ip,
        "hours": hours,
        "all_point_count": len(timestamps),
        "window_start": timestamps[0] if timestamps else "--",
        "window_end": timestamps[-1] if timestamps else "--",
        "stats_from_all_points": stats,
    }

    system_prompt = (
        "你是K8S节点资源监控分析助手。输出必须是纯文本单段总结，不超过200个中文字符。"
        "仅围绕CPU与内存资源使用情况，说明CPU使用率、内存使用率以及CPU核/内存GB用量的增减方向与关键变化量；禁止Markdown和分点。"
        "必须输出完整句，不允许冒号结尾、字段列到一半、半句话被截断。"
        "开头必须明确写出节点名称和统计时间范围（近X小时）。"
    )
    user_prompt = (
        "请基于以下统计生成一段精炼总结（<=200字）。"
        "要说明CPU与内存资源使用情况，并给出CPU使用率、内存使用率以及CPU核/内存GB用量变化。"
        f"首句必须包含“节点{node_ip}在近{hours}小时内”。"
        "若信息过多，请主动压缩措辞，不要省略成未完成字段。"
        "不要换行，不要使用列表符号。\n\n"
        "输入数据(JSON，已基于当前节点与所选时间范围全部时间节点统计):\n"
        + json.dumps(prompt_payload, ensure_ascii=False)
    )

    endpoint = str(ai_config["base_url"]).rstrip("/") + "/chat/completions"
    _validate_https_endpoint(endpoint)
    request_body = {
        "model": ai_config["model"],
        "temperature": ai_config["temperature"],
        "top_p": ai_config["top_p"],
        "stream": True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {ai_config['api_key']}",
        "Content-Type": "application/json",
    }

    response = None
    try:
        response = requests.post(
            endpoint,
            json=request_body,
            headers=headers,
            timeout=int(ai_config["timeout_seconds"]),
            verify=bool(ai_config.get("verify_tls", True)),
            stream=True,
        )
    except requests.RequestException as exc:
        raise MonitoringServiceError(f"AI请求失败: {exc}") from exc

    if response.status_code >= 400:
        error_text = response.text[:400]
        raise MonitoringServiceError(f"AI接口返回异常 HTTP {response.status_code}: {error_text}")

    content_type = str(response.headers.get("Content-Type") or "").lower()
    try:
        if "text/event-stream" in content_type:
            yielded = False
            for raw_line in response.iter_lines(decode_unicode=False):
                if isinstance(raw_line, (bytes, bytearray)):
                    line = raw_line.decode("utf-8", errors="replace").strip()
                else:
                    line = str(raw_line or "").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if not data_text:
                    continue
                if data_text == "[DONE]":
                    break
                try:
                    payload = json.loads(data_text)
                except ValueError:
                    continue
                delta_text = _extract_stream_delta_text(payload)
                if delta_text:
                    yielded = True
                    yield delta_text
            if yielded:
                return
            raise MonitoringServiceError("AI流式响应为空")

        try:
            payload = response.json()
        except ValueError as exc:
            raise MonitoringServiceError("AI接口返回非JSON数据") from exc
        text = _extract_nonstream_content(payload)
        if not text:
            raise MonitoringServiceError("AI接口返回内容为空")
        yield text
    finally:
        if response is not None:
            response.close()


def _extract_stream_delta_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
    content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        )
    return ""


def _extract_nonstream_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text = "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        )
        return text.strip()
    return ""


def _complete_summary_text(text: str, max_chars: int) -> str:
    source = str(text or "").strip()
    if not source:
        return ""

    source = re.sub(r"\r\n?", "\n", source)
    source = re.sub(r"^#{1,6}\s*", "", source, flags=re.MULTILINE)
    source = re.sub(r"\*\*(.*?)\*\*", r"\1", source)
    source = re.sub(r"`{1,3}", "", source)
    source = re.sub(r"^\s*[*-]\s+", "", source, flags=re.MULTILINE)
    source = re.sub(r"\s*\n\s*", " ", source)
    source = re.sub(r"\s+", " ", source).strip()
    source = source.replace(" :", "：").replace(": ", "：")
    source = source.rstrip("，,；;：:、 ")
    limit = max(60, int(max_chars))

    if len(source) <= limit:
        return _ensure_summary_tail(source)

    sentence_parts = re.findall(r"[^。！？!?；;]+[。！？!?；;]?", source)
    built = ""
    for part in sentence_parts:
        candidate = (built + part).strip()
        if candidate and len(candidate) <= limit:
            built = candidate
        else:
            break
    if built:
        return _ensure_summary_tail(built)

    clause_parts = re.findall(r"[^，,。！？!?；;]+[，,。！？!?；;]?", source)
    built = ""
    for part in clause_parts:
        cleaned_part = part.strip()
        if not cleaned_part:
            continue
        candidate = cleaned_part if not built else built.rstrip("，,；;。！？!? ") + "，" + cleaned_part.lstrip("，,；;。！？!? ")
        if len(candidate) <= limit:
            built = candidate
        else:
            break
    if built:
        return _ensure_summary_tail(built)

    compact = source[:limit]
    compact = re.sub(r"(CPU核|内存用量|POD数量|CPU使用率|内存使用率)[：:]\s*$", "", compact)
    compact = re.sub(r"[，,；;：:、\s]+$", "", compact)
    punctuation_index = max(compact.rfind("。"), compact.rfind("；"), compact.rfind("，"))
    if punctuation_index >= max(20, limit // 3):
        compact = compact[: punctuation_index + 1]
    return _ensure_summary_tail(compact)


def _complete_summary_with_scope(
    text: str,
    *,
    scope_label: str,
    scope_value: str,
    hours: int,
    max_chars: int,
) -> str:
    source = str(text or "").strip()
    if not source:
        return ""

    clean_scope_label = str(scope_label or "").strip() or "对象"
    clean_scope_value = str(scope_value or "").strip() or "--"
    window_hours = max(1, int(hours or 24))

    # Remove duplicated leading context from model output, then prepend normalized context.
    source = re.sub(rf"^\s*{re.escape(clean_scope_label)}\s*{re.escape(clean_scope_value)}\s*在近?\s*\d+\s*小时内[，,:：\s]*", "", source)
    source = re.sub(rf"^\s*{re.escape(clean_scope_label)}\s*{re.escape(clean_scope_value)}[，,:：\s]*", "", source)
    source = re.sub(r"^\s*在近?\s*\d+\s*小时内[，,:：\s]*", "", source)

    prefix = f"{clean_scope_label}{clean_scope_value}在近{window_hours}小时内，"
    combined = prefix + source.lstrip("，,:：。；; ")
    return _complete_summary_text(combined, max_chars)


def _ensure_summary_tail(text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return ""
    source = re.sub(r"(CPU核|内存用量|POD数量|CPU使用率|内存使用率)[：:]\s*$", "", source)
    source = re.sub(r"[，,；;：:、\s]+$", "", source)
    if not source:
        return ""
    if source[-1] not in "。！？!?":
        source += "。"
    return source


def _chunk_text(text: str, chunk_size: int = 120) -> Iterator[str]:
    source = str(text or "")
    if not source:
        return
    step = max(20, chunk_size)
    for idx in range(0, len(source), step):
        yield source[idx: idx + step]

