from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone


AUTH_QUEUE_COLUMNS = [
    "FId",
    "OD_SERIAL_NUMBER",
    "OD_CONTRACT_NUMBER",
    "OD_BMPID",
    "AutoAuthFlag",
    "Remark",
    "CreateTime",
    "AutoAuthHandleTime",
    "AutoAuthHandleResult",
    "AutoAuthHandleResultDesc",
]

AUTH_QUEUE_SEARCH_COLUMNS = [
    "OD_SERIAL_NUMBER",
    "OD_CONTRACT_NUMBER",
    "OD_BMPID",
    "AutoAuthFlag",
    "AutoAuthHandleResult",
    "Remark",
    "AutoAuthHandleResultDesc",
]


def _get_config():
    cfg = getattr(settings, "SQLSERVER_AUTH", {}) or {}
    required = ("HOST", "USER", "PASSWORD", "NAME")
    missing = [key for key in required if not str(cfg.get(key, "")).strip()]
    if missing:
        raise ImproperlyConfigured(f"SQLSERVER_AUTH 缺少配置: {', '.join(missing)}")
    return cfg


def _connect():
    try:
        import pymssql
    except Exception as exc:  # pragma: no cover
        raise ImproperlyConfigured("未安装 pymssql，请先安装依赖。") from exc

    cfg = _get_config()
    return pymssql.connect(
        server=f"{cfg['HOST']}:{int(cfg.get('PORT', 1433))}",
        user=cfg["USER"],
        password=cfg["PASSWORD"],
        database=cfg["NAME"],
        charset=cfg.get("CHARSET", "utf8"),
        login_timeout=int(cfg.get("LOGIN_TIMEOUT", 5)),
        timeout=int(cfg.get("QUERY_TIMEOUT", 20)),
        as_dict=True,
        tds_version=str(cfg.get("TDS_VERSION", "7.0")),
    )


def _rows_to_dict(cursor):
    return list(cursor.fetchall())


def _rows_to_namespace(rows, columns):
    return [SimpleNamespace(**{key: row.get(key) for key in columns}) for row in rows]


def _normalize_text(value):
    return str(value or "").strip().lower()


def _resolve_result_bucket(value, success_values, failure_values):
    normalized = _normalize_text(value)
    if not normalized:
        return ""
    success_tokens = [_normalize_text(token) for token in success_values]
    failure_tokens = [_normalize_text(token) for token in failure_values]
    if any(token and token in normalized for token in success_tokens):
        return "success"
    if any(token and token in normalized for token in failure_tokens):
        return "failure"
    return ""


def _to_local_date(value):
    if not value:
        return None
    if timezone.is_aware(value):
        return timezone.localtime(value).date()
    if hasattr(value, "date"):
        return value.date()
    return None


def fetch_authorization_record_rows(search_text=""):
    keyword = (search_text or "").strip()
    sql = f"""
        SELECT {", ".join([f'[{column}]' for column in AUTH_QUEUE_COLUMNS])}
        FROM [OrderAutoAuthorizationQueue]
    """
    params = []
    if keyword:
        like_value = f"%{keyword}%"
        where_clause = " OR ".join([f"[{column}] LIKE %s" for column in AUTH_QUEUE_SEARCH_COLUMNS])
        sql += f" WHERE {where_clause}"
        params = [like_value] * len(AUTH_QUEUE_SEARCH_COLUMNS)
    sql += " ORDER BY [FId] DESC"

    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            rows = _rows_to_dict(cursor)
    finally:
        conn.close()

    return _rows_to_namespace(rows, AUTH_QUEUE_COLUMNS)


def fetch_authorization_record_summary(success_values=(), failure_values=()):
    sql = """
        SELECT [AutoAuthHandleResult], [AutoAuthHandleTime]
        FROM [OrderAutoAuthorizationQueue]
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = _rows_to_dict(cursor)
    finally:
        conn.close()

    today = timezone.localdate()
    total_success = 0
    total_failure = 0
    today_success = 0
    today_failure = 0

    for row in rows:
        bucket = _resolve_result_bucket(row.get("AutoAuthHandleResult"), success_values, failure_values)
        handle_date = _to_local_date(row.get("AutoAuthHandleTime"))
        if bucket == "success":
            total_success += 1
            if handle_date == today:
                today_success += 1
        elif bucket == "failure":
            total_failure += 1
            if handle_date == today:
                today_failure += 1

    return {
        "total_success": total_success,
        "total_failure": total_failure,
        "today_success": today_success,
        "today_failure": today_failure,
    }


def fetch_authorization_record_trend(*, days=30, success_values=(), failure_values=()):
    window_days = max(1, min(int(days or 30), 90))
    today = timezone.localdate()
    start_date = today - timedelta(days=window_days - 1)

    sql = """
        SELECT [CreateTime], [AutoAuthHandleTime], [AutoAuthHandleResult]
        FROM [OrderAutoAuthorizationQueue]
        WHERE COALESCE([AutoAuthHandleTime], [CreateTime]) >= DATEADD(day, %s, CONVERT(date, GETDATE()))
    """

    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (-(window_days - 1),))
            rows = _rows_to_dict(cursor)
    finally:
        conn.close()

    trend_map = {}
    for offset in range(window_days):
        bucket_date = start_date + timedelta(days=offset)
        trend_map[bucket_date] = {
            "date": bucket_date.isoformat(),
            "success": 0,
            "failure": 0,
            "pending": 0,
        }

    for row in rows:
        event_date = _to_local_date(row.get("AutoAuthHandleTime")) or _to_local_date(row.get("CreateTime"))
        if not event_date or event_date < start_date or event_date > today:
            continue

        bucket = _resolve_result_bucket(row.get("AutoAuthHandleResult"), success_values, failure_values)
        if bucket not in ("success", "failure"):
            bucket = "pending"
        trend_map[event_date][bucket] += 1

    return [trend_map[start_date + timedelta(days=offset)] for offset in range(window_days)]
