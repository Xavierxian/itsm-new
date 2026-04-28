from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


CUSTOMER_COLUMNS = [
    "CU_ID",
    "CU_SRCCODE",
    "CU_ORGCODE",
    "CU_CODE",
    "CU_NAME",
    "CU_ADDR",
    "CU_CONTACT",
    "CU_EMAIL",
    "CU_MOBILE",
    "CU_OTHER",
    "CU_BRAND",
    "CU_STATE",
    "CU_REMARK",
    "CU_FORBIT_DATE",
    "CU_FORBIT_ID",
    "CU_FORBIT_USER",
    "CU_CREATE_DATE",
    "CU_CREATE_ID",
    "CU_CREATE_USER",
    "CU_MODIFY_DATE",
    "CU_MODIFY_ID",
    "CU_MODIFY_USER",
]

LICENSE_COLUMNS = [
    "LIC_ID",
    "LIC_LICENSEID",
    "LIC_ACCOUNT",
    "LIC_LICENSEINFO",
    "LIC_PASSWORD",
    "LIC_CUID",
    "LIC_CUNAME",
    "LIC_SERIAL",
    "LIC_ORDERID",
    "LIC_PTID",
    "LIC_TYPE",
    "LIC_TYPEINFO",
    "LIC_ACTIVE",
    "LIC_START",
    "LIC_END",
    "LIC_USECOUNT",
    "LIC_NUM",
    "LIC_BIND",
    "LIC_STATE",
    "LIC_FORBIT_DATE",
    "LIC_FORBIT_ID",
    "LIC_FORBIT_USER",
    "LIC_CREATE_DATE",
    "LIC_CREATE_ID",
    "LIC_CREATE_USER",
    "LIC_MODIFY_DATE",
    "LIC_MODIFY_ID",
    "LIC_MODIFY_USER",
    "LIC_REG_DATE",
    "LIC_REG_IP",
    "LIC_REMARK",
    "LIC_ACTIVATION_CODE",
    "LIC_ORDERNUMBER",
    "LIC_BMP_NUMBER",
]

LICENSEDETAIL_COLUMNS = [
    "LICD_ID",
    "LICD_MAINID",
    "LICD_DSRCCODE",
    "LICD_SRCCUNAME",
    "LICD_INCUID",
    "LICD_PTID",
    "LICD_PTNAME",
    "LICD_MDID",
    "LICD_MDNAME",
    "LICD_COUNT",
    "LICD_TYPE",
    "LICD_TYPEINFO",
    "LICD_START",
    "LICD_END",
    "LICD_USECOUNT",
    "LICD_STATE",
    "LICD_FORBIT_DATE",
    "LICD_FORBIT_ID",
    "LICD_FORBIT_USER",
    "LICD_CREATE_DATE",
    "LICD_CREATE_ID",
    "LICD_CREATE_USER",
    "LICD_MODIFY_DATE",
    "LICD_MODIFY_ID",
    "LICD_MODIFY_USER",
    "LICD_REMARK",
    "LICD_ORDERID",
    "LICD_ORDERNUMBER",
]

CUSTOMER_SUGGEST_COLUMNS = [
    "CU_NAME",
    "CU_CODE",
    "CU_ORGCODE",
]

MODULE_COLUMNS = [
    "MD_ID",
    "MD_CODE",
    "MD_NAME",
    "MD_PRODUCTID",
    "MD_PRODUCTCODE",
    "MD_ISPOINT",
    "MD_PRICE",
    "MD_STATE",
    "MD_REMARK",
    "MD_FORBIT_USER",
    "MD_CREATE_USER",
    "MD_MODIFY_USER",
    "MD_CREATE_DATE",
]


def _get_config():
    cfg = getattr(settings, "MYSQL_AUTH", {}) or {}
    required = ("HOST", "USER", "PASSWORD", "NAME")
    missing = [key for key in required if not str(cfg.get(key, "")).strip()]
    if missing:
        raise ImproperlyConfigured(f"MYSQL_AUTH 缺少配置: {', '.join(missing)}")
    return cfg


def _connect():
    try:
        import pymysql
    except Exception as exc:  # pragma: no cover
        raise ImproperlyConfigured("未安装 PyMySQL，请先安装依赖。") from exc

    cfg = _get_config()
    return pymysql.connect(
        host=cfg["HOST"],
        port=int(cfg.get("PORT", 3306)),
        user=cfg["USER"],
        password=cfg["PASSWORD"],
        database=cfg["NAME"],
        charset=cfg.get("CHARSET", "utf8mb4"),
        connect_timeout=int(cfg.get("LOGIN_TIMEOUT", 5)),
        read_timeout=int(cfg.get("QUERY_TIMEOUT", 20)),
        write_timeout=int(cfg.get("QUERY_TIMEOUT", 20)),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _rows_to_namespace(rows, columns):
    result = []
    for row in rows:
        result.append(SimpleNamespace(**{key: row.get(key) for key in columns}))
    return result


def _merge_rows(primary_rows, extra_rows, key_field):
    merged = []
    seen = set()
    for row in list(primary_rows) + list(extra_rows):
        key = row.get(key_field)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def _normalize_customer_ids(*row_groups):
    values = []
    seen = set()
    for rows, field in row_groups:
        for row in rows:
            raw = row.get(field)
            if raw in (None, ""):
                continue
            text = str(raw).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            values.append(text)
    return values


def _fetch_rows_by_customer_ids(cursor, table_name, columns, id_column, customer_ids):
    if not customer_ids:
        return []
    placeholders = ", ".join(["%s"] * len(customer_ids))
    sql = f"""
        SELECT {", ".join([f'`{c}`' for c in columns])}
        FROM `{table_name}`
        WHERE `{id_column}` IN ({placeholders})
        ORDER BY `{columns[0]}` DESC
    """
    cursor.execute(sql, tuple(customer_ids))
    return cursor.fetchall()


def _format_datetime_for_display(value):
    if value in (None, ""):
        return "-"
    text = str(value).strip()
    if not text:
        return "-"
    return text.replace("-", "/")[:16]


def fetch_module_rows(search_text=""):
    keyword = (search_text or "").strip()
    select_sql = f"""
        SELECT {", ".join([f'`{c}`' for c in MODULE_COLUMNS])}
        FROM `cljc_module`
    """
    params = []
    if keyword:
        like_pattern = f"%{keyword}%"
        select_sql += """
            WHERE
                `MD_CODE` LIKE %s
                OR `MD_NAME` LIKE %s
                OR `MD_PRODUCTCODE` LIKE %s
                OR `MD_REMARK` LIKE %s
                OR `MD_FORBIT_USER` LIKE %s
                OR `MD_CREATE_USER` LIKE %s
                OR `MD_MODIFY_USER` LIKE %s
                OR CAST(`MD_PRODUCTID` AS CHAR) LIKE %s
        """
        params = [like_pattern] * 8
    select_sql += " ORDER BY `MD_ID` DESC"

    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(select_sql, tuple(params))
            rows = cursor.fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        result.append(
            SimpleNamespace(
                pk=row.get("MD_ID"),
                id=row.get("MD_ID"),
                md_code=row.get("MD_CODE"),
                md_name=row.get("MD_NAME"),
                md_productid=row.get("MD_PRODUCTID"),
                md_productcode=row.get("MD_PRODUCTCODE"),
                md_ispoint=row.get("MD_ISPOINT"),
                md_price=row.get("MD_PRICE"),
                md_state=row.get("MD_STATE"),
                md_remark=row.get("MD_REMARK"),
                md_forbit_user=row.get("MD_FORBIT_USER"),
                md_create_user=row.get("MD_CREATE_USER"),
                md_modify_user=row.get("MD_MODIFY_USER"),
                md_create_date_display=_format_datetime_for_display(row.get("MD_CREATE_DATE")),
            )
        )
    return result


def fetch_authorization_detail_sets(customer_name=""):
    name = (customer_name or "").strip()
    if not name:
        return {"customer_rows": [], "license_rows": [], "licensedetail_rows": []}
    like_name = f"%{name}%"

    customer_sql = f"""
        SELECT {", ".join([f'`{c}`' for c in CUSTOMER_COLUMNS])}
        FROM `cljc_customer`
        WHERE `CU_NAME` LIKE %s
        ORDER BY `CU_ID` DESC
    """
    license_sql = f"""
        SELECT {", ".join([f'`{c}`' for c in LICENSE_COLUMNS])}
        FROM `cljc_license`
        WHERE `LIC_CUNAME` LIKE %s
        ORDER BY `LIC_ID` DESC
    """
    licensedetail_sql = f"""
        SELECT {", ".join([f'`{c}`' for c in LICENSEDETAIL_COLUMNS])}
        FROM `cljc_licensedetail`
        WHERE `LICD_SRCCUNAME` LIKE %s
        ORDER BY `LICD_ID` DESC
    """

    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(customer_sql, (like_name,))
            customer_rows = cursor.fetchall()

            cursor.execute(license_sql, (like_name,))
            license_rows = cursor.fetchall()

            cursor.execute(licensedetail_sql, (like_name,))
            licensedetail_rows = cursor.fetchall()

            customer_ids = _normalize_customer_ids(
                (customer_rows, "CU_ID"),
                (license_rows, "LIC_CUID"),
                (licensedetail_rows, "LICD_INCUID"),
            )
            if customer_ids:
                customer_rows = _merge_rows(
                    customer_rows,
                    _fetch_rows_by_customer_ids(
                        cursor,
                        "cljc_customer",
                        CUSTOMER_COLUMNS,
                        "CU_ID",
                        customer_ids,
                    ),
                    "CU_ID",
                )
                license_rows = _merge_rows(
                    license_rows,
                    _fetch_rows_by_customer_ids(
                        cursor,
                        "cljc_license",
                        LICENSE_COLUMNS,
                        "LIC_CUID",
                        customer_ids,
                    ),
                    "LIC_ID",
                )
                licensedetail_rows = _merge_rows(
                    licensedetail_rows,
                    _fetch_rows_by_customer_ids(
                        cursor,
                        "cljc_licensedetail",
                        LICENSEDETAIL_COLUMNS,
                        "LICD_INCUID",
                        customer_ids,
                    ),
                    "LICD_ID",
                )
    finally:
        conn.close()

    return {
        "customer_rows": _rows_to_namespace(customer_rows, CUSTOMER_COLUMNS),
        "license_rows": _rows_to_namespace(license_rows, LICENSE_COLUMNS),
        "licensedetail_rows": _rows_to_namespace(licensedetail_rows, LICENSEDETAIL_COLUMNS),
    }


def fetch_authorization_customer_suggestions(keyword="", limit=12):
    text = (keyword or "").strip()
    if not text:
        return []

    try:
        limit_int = int(limit)
    except (TypeError, ValueError):
        limit_int = 12
    limit_int = max(1, min(limit_int, 50))

    sql = f"""
        SELECT DISTINCT {", ".join([f'`{c}`' for c in CUSTOMER_SUGGEST_COLUMNS])}
        FROM `cljc_customer`
        WHERE `CU_NAME` LIKE %s
        ORDER BY `CU_NAME` ASC
        LIMIT {limit_int}
    """

    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (f"%{text}%",))
            rows = cursor.fetchall()
    finally:
        conn.close()

    return _rows_to_namespace(rows, CUSTOMER_SUGGEST_COLUMNS)
