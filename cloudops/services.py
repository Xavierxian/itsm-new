from __future__ import annotations

import ipaddress
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
from core.cache_helpers import cache_delete, cache_get, cache_set


def _env_text(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    cleaned = str(value).strip()
    return cleaned if cleaned else default


def _env_int(name: str, default: int) -> int:
    raw = _env_text(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env_text(name, "")
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = _to_text(value)
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _looks_like_ip(value: Any) -> bool:
    text = _to_text(value)
    if not text:
        return False
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def _normalize_host_name_ip(host_name: Any, host_ip: Any) -> tuple[str, str]:
    host_name_value = _to_text(host_name)
    host_ip_value = _to_text(host_ip)
    if _looks_like_ip(host_name_value) and (
        not host_ip_value or host_ip_value.casefold() == host_name_value.casefold()
    ):
        host_ip_value = host_name_value
        host_name_value = ""
    return host_name_value, host_ip_value


class JumpServerAPIError(Exception):
    def __init__(self, message: str, *, status_code: int = 500, details: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


@dataclass(frozen=True)
class JumpServerConfig:
    api_endpoint: str
    access_key_id: str
    access_key_secret: str
    token_expire_seconds: int
    request_timeout_seconds: int
    hosts_cache_ttl: int
    credentials_cache_ttl: int
    online_count_cache_ttl: int
    summary_cache_ttl: int
    default_cloud_id: str
    default_user_id: str
    default_team_id: str
    default_page: str
    oauth_expire_seconds: int
    verify_tls: bool
    allow_insecure_http: bool
    request_retries: int
    retry_backoff_seconds: float

    @classmethod
    def from_env(cls) -> "JumpServerConfig":
        endpoint = _env_text("JUMPSERVER_API_ENDPOINT", "https://jump.baison.net/api/openapi").rstrip("/")
        return cls(
            api_endpoint=endpoint,
            access_key_id=_env_text("JUMPSERVER_ACCESS_KEY_ID", ""),
            access_key_secret=_env_text("JUMPSERVER_ACCESS_KEY_SECRET", ""),
            token_expire_seconds=_env_int("JUMPSERVER_TOKEN_EXPIRE_SECONDS", 3600),
            request_timeout_seconds=_env_int("JUMPSERVER_TIMEOUT_SECONDS", 10),
            hosts_cache_ttl=_env_int("JUMPSERVER_HOSTS_CACHE_TTL", 300),
            credentials_cache_ttl=_env_int("JUMPSERVER_CREDENTIALS_CACHE_TTL", 300),
            online_count_cache_ttl=_env_int("JUMPSERVER_ONLINE_CACHE_TTL", 20),
            summary_cache_ttl=_env_int("JUMPSERVER_SUMMARY_CACHE_TTL", 30),
            default_cloud_id=_env_text("JUMPSERVER_DEFAULT_CLOUD_ID", "49149403766784"),
            default_user_id=_env_text("JUMPSERVER_DEFAULT_USER_ID", "168692671705088"),
            default_team_id=_env_text("JUMPSERVER_DEFAULT_TEAM_ID", "1"),
            default_page=_env_text("JUMPSERVER_DEFAULT_PAGE", "Home"),
            oauth_expire_seconds=_env_int("JUMPSERVER_OAUTH_EXPIRE_SECONDS", 600),
            verify_tls=_env_bool("JUMPSERVER_VERIFY_TLS", True),
            allow_insecure_http=_env_bool("ALLOW_INSECURE_UPSTREAM_HTTP", False),
            request_retries=max(0, _env_int("JUMPSERVER_REQUEST_RETRIES", 2)),
            retry_backoff_seconds=float(_env_text("JUMPSERVER_RETRY_BACKOFF_SECONDS", "0.5")),
        )


class JumpServerClient:
    def __init__(self, config: JumpServerConfig | None = None):
        self.config = config or JumpServerConfig.from_env()

    def _assert_transport_security(self) -> None:
        scheme = urlparse(self.config.api_endpoint).scheme.lower()
        if scheme == "https":
            return
        if self.config.allow_insecure_http:
            return
        raise JumpServerAPIError(
            "JumpServer API endpoint must use HTTPS. Set ALLOW_INSECURE_UPSTREAM_HTTP=true only for approved intranet exceptions.",
            status_code=500,
        )

    @property
    def configured(self) -> bool:
        return bool(self.config.access_key_id and self.config.access_key_secret)

    def ensure_configured(self) -> None:
        if self.configured:
            self._assert_transport_security()
            return
        raise JumpServerAPIError(
            "JumpServer API 凭据未配置，请检查环境变量 JUMPSERVER_ACCESS_KEY_ID / JUMPSERVER_ACCESS_KEY_SECRET",
            status_code=500,
        )

    def _token_cache_key(self) -> str:
        fingerprint = self.config.access_key_id[:8] if self.config.access_key_id else "missing"
        return f"cloudops.jumpserver.token.{fingerprint}"

    def _hosts_cache_key(self, cloud_id: str) -> str:
        return f"cloudops.jumpserver.hosts.{cloud_id}"

    def _credentials_cache_key(self, host_id: str) -> str:
        return f"cloudops.jumpserver.credentials.{host_id}"

    def _online_cache_key(self) -> str:
        return "cloudops.jumpserver.online-count"

    def _summary_cache_key(self, cloud_id: str) -> str:
        return f"cloudops.jumpserver.summary.{cloud_id}"

    def _get_token(self, *, force_refresh: bool = False) -> str:
        self.ensure_configured()
        cache_key = self._token_cache_key()

        if not force_refresh:
            cached = cache_get(cache_key)
            if isinstance(cached, dict):
                token = _to_text(cached.get("token"))
                expires_at = float(cached.get("expires_at") or 0)
                if token and expires_at - time.time() > 30:
                    return token

        token_url = f"{self.config.api_endpoint}/oauth"
        token_payload = {
            "accessKeyId": self.config.access_key_id,
            "accessKeySecret": self.config.access_key_secret,
            "expireSeconds": self.config.token_expire_seconds,
        }
        response = None

        try:
            response = requests.post(
                token_url,
                json=token_payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=self.config.request_timeout_seconds,
                verify=self.config.verify_tls,
            )
        except requests.RequestException as exc:
            raise JumpServerAPIError("请求 JumpServer Token 失败", status_code=502, details=str(exc)) from exc

        # Backward compatibility: some JumpServer OpenAPI deployments only support
        # token retrieval via query parameters and return 405 for POST /oauth.
        if response is not None and response.status_code == 405:
            try:
                response = requests.get(
                    token_url,
                    params=token_payload,
                    headers={"Accept": "application/json"},
                    timeout=self.config.request_timeout_seconds,
                    verify=self.config.verify_tls,
                )
            except requests.RequestException as exc:
                raise JumpServerAPIError(
                    "请求 JumpServer Token 失败（POST/GET 兼容重试均失败）",
                    status_code=502,
                    details=str(exc),
                ) from exc

        if response.status_code != 200:
            raise JumpServerAPIError(
                "获取 JumpServer Token 失败",
                status_code=response.status_code,
                details=response.text,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise JumpServerAPIError("JumpServer Token 响应格式错误", status_code=502, details=response.text) from exc

        token = _to_text(payload.get("token"))
        if not token:
            raise JumpServerAPIError("JumpServer Token 为空", status_code=502)

        expires_at = time.time() + max(60, self.config.token_expire_seconds)
        cache_set(cache_key, {"token": token, "expires_at": expires_at}, timeout=self.config.token_expire_seconds)
        return token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        retry_on_unauthorized: bool = True,
    ) -> Any:
        url = f"{self.config.api_endpoint}{path}"
        token = self._get_token(force_refresh=False)
        headers = {
            "Accept": "application/json",
            "Authorization": token,
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        response = None
        last_exception = None
        retries = max(0, self.config.request_retries)
        for attempt in range(retries + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=self.config.request_timeout_seconds,
                    verify=self.config.verify_tls,
                )
                break
            except requests.RequestException as exc:
                last_exception = exc
                if attempt >= retries:
                    raise JumpServerAPIError("调用 JumpServer API 失败", status_code=502, details=str(exc)) from exc
                time.sleep(max(0.1, self.config.retry_backoff_seconds) * (attempt + 1))

        if response is None:
            raise JumpServerAPIError("调用 JumpServer API 失败", status_code=502, details=str(last_exception or "unknown"))

        if response.status_code == 401 and retry_on_unauthorized:
            cache_delete(self._token_cache_key())
            return self._request(
                method=method,
                path=path,
                params=params,
                json_body=json_body,
                expected_statuses=expected_statuses,
                retry_on_unauthorized=False,
            )

        if response.status_code not in expected_statuses:
            raise JumpServerAPIError(
                f"JumpServer API 请求失败: {path}",
                status_code=response.status_code,
                details=response.text,
            )

        if response.status_code == 204 or not response.content:
            return {}

        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def _normalize_online(self, host_item: dict[str, Any]) -> bool | None:
        for key in ("isOnline", "online", "connected", "alive"):
            if key in host_item:
                value = host_item.get(key)
                if isinstance(value, bool):
                    return value
                if isinstance(value, (int, float)):
                    return bool(value)
                text = _to_text(value).lower()
                if text in {"true", "1", "yes", "on", "online", "active", "running", "up"}:
                    return True
                if text in {"false", "0", "no", "off", "offline", "inactive", "down"}:
                    return False

        status_text = _to_text(host_item.get("status") or host_item.get("state")).lower()
        if status_text:
            if status_text in {"online", "active", "running", "up"}:
                return True
            if status_text in {"offline", "inactive", "down", "stopped"}:
                return False
        return None

    def list_hosts(self, cloud_id: str | None = None, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        cloud_id_value = _to_text(cloud_id or self.config.default_cloud_id)
        if not cloud_id_value:
            raise JumpServerAPIError("未提供 cloud_id，无法查询堡垒机主机清单", status_code=400)

        cache_key = self._hosts_cache_key(cloud_id_value)
        if not force_refresh:
            cached = cache_get(cache_key)
            if isinstance(cached, list):
                normalized_cached: list[dict[str, Any]] = []
                has_changed = False
                for row in cached:
                    if not isinstance(row, dict):
                        continue
                    host_name, host_ip = _normalize_host_name_ip(row.get("hostName"), row.get("hostIp"))
                    if host_name != _to_text(row.get("hostName")) or host_ip != _to_text(row.get("hostIp")):
                        has_changed = True
                    row_copy = dict(row)
                    row_copy["hostName"] = host_name
                    row_copy["hostIp"] = host_ip
                    normalized_cached.append(row_copy)
                if has_changed:
                    cache_set(cache_key, normalized_cached, timeout=self.config.hosts_cache_ttl)
                return normalized_cached

        data = self._request(
            "GET",
            f"/host/byCloud/{cloud_id_value}",
            params={"page": 1, "size": 100000},
            expected_statuses=(200,),
        )

        raw_hosts = data.get("hosts", []) if isinstance(data, dict) else []
        hosts: list[dict[str, Any]] = []
        for item in raw_hosts:
            if not isinstance(item, dict):
                continue
            host_id = _to_text(item.get("hostId") or item.get("id"))
            if not host_id:
                continue

            host_name, host_ip = _normalize_host_name_ip(
                item.get("hostName") or item.get("name"),
                item.get("hostIp") or item.get("ip") or item.get("host"),
            )

            hosts.append(
                {
                    "hostId": host_id,
                    "hostName": host_name,
                    "hostIp": host_ip,
                    "operatingSystem": _to_text(item.get("operatingSystem") or item.get("os") or item.get("system")),
                    "description": _to_text(item.get("description") or item.get("remark")),
                    "status": _to_text(item.get("status") or item.get("state")),
                    "online": self._normalize_online(item),
                    "credentialCount": _parse_int(item.get("credentialCount")),
                }
            )

        hosts.sort(
            key=lambda row: (
                (row.get("hostName") or row.get("hostIp") or "").casefold(),
                row.get("hostId", ""),
            )
        )
        cache_set(cache_key, hosts, timeout=self.config.hosts_cache_ttl)
        return hosts

    def clear_hosts_cache(self, cloud_id: str | None = None) -> None:
        cloud_id_value = _to_text(cloud_id or self.config.default_cloud_id)
        if cloud_id_value:
            cache_delete(self._hosts_cache_key(cloud_id_value))
            cache_delete(self._summary_cache_key(cloud_id_value))

    def resolve_host_id(self, identifier: str, *, cloud_id: str | None = None, hosts: list[dict[str, Any]] | None = None) -> str:
        keyword = _to_text(identifier)
        if not keyword:
            raise JumpServerAPIError("请输入主机标识（Host ID / 主机名 / 主机IP）", status_code=400)

        host_rows = hosts if hosts is not None else self.list_hosts(cloud_id=cloud_id, force_refresh=False)
        normalized = keyword.casefold()

        for host in host_rows:
            if _to_text(host.get("hostId")).casefold() == normalized:
                return _to_text(host.get("hostId"))

        for host in host_rows:
            if _to_text(host.get("hostName")).casefold() == normalized:
                return _to_text(host.get("hostId"))
            if _to_text(host.get("hostIp")).casefold() == normalized:
                return _to_text(host.get("hostId"))

        partial_matches = []
        for host in host_rows:
            aggregate = " ".join(
                [
                    _to_text(host.get("hostId")),
                    _to_text(host.get("hostName")),
                    _to_text(host.get("hostIp")),
                    _to_text(host.get("description")),
                ]
            ).casefold()
            if normalized in aggregate:
                partial_matches.append(host)

        if len(partial_matches) == 1:
            return _to_text(partial_matches[0].get("hostId"))
        if len(partial_matches) > 1:
            raise JumpServerAPIError("匹配到多个主机，请输入更精确的主机标识", status_code=400)
        raise JumpServerAPIError("未匹配到目标主机，请检查输入", status_code=404)

    def get_credentials(self, host_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        host_id_value = _to_text(host_id)
        if not host_id_value:
            raise JumpServerAPIError("host_id 不能为空", status_code=400)

        cache_key = self._credentials_cache_key(host_id_value)
        if not force_refresh:
            cached = cache_get(cache_key)
            if isinstance(cached, dict):
                return cached

        data = self._request(
            "GET",
            f"/credential/byHost/{host_id_value}",
            params={"isPasswordProvide": "false", "encryptSensitive": "false"},
            expected_statuses=(200,),
        )
        payload = data if isinstance(data, dict) else {"data": data}
        cache_set(cache_key, payload, timeout=self.config.credentials_cache_ttl)
        return payload

    def _extract_total(self, payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        for key in ("total", "totalCount", "count", "recordsTotal"):
            value = _parse_int(payload.get(key))
            if value is not None:
                return value
        return None

    def count_online_users(self) -> int:
        cache_key = self._online_cache_key()
        cached = cache_get(cache_key)
        if isinstance(cached, int):
            return cached

        data = self._request("GET", "/users/countOnline", expected_statuses=(200,))
        count = 0
        if isinstance(data, dict):
            parsed = _parse_int(data.get("count"))
            if parsed is not None:
                count = parsed
        cache_set(cache_key, count, timeout=self.config.online_count_cache_ttl)
        return count

    def count_users(self) -> int | None:
        team_id = _to_text(self.config.default_team_id)
        if team_id:
            try:
                data = self._request(
                    "GET",
                    "/user/byTeam",
                    params={"teamId": team_id, "page": 1, "size": 1},
                    expected_statuses=(200,),
                )
                total = self._extract_total(data)
                if total is not None:
                    return total
            except JumpServerAPIError:
                pass

        try:
            data = self._request("GET", "/users", params={"page": 1, "size": 1}, expected_statuses=(200,))
        except JumpServerAPIError:
            return None
        return self._extract_total(data)

    def count_credentials(self) -> int | None:
        team_id = _to_text(self.config.default_team_id)
        if not team_id:
            return None
        try:
            data = self._request(
                "GET",
                f"/credential/byTeam/{team_id}",
                params={"page": 1, "size": 1},
                expected_statuses=(200,),
            )
        except JumpServerAPIError:
            return None
        return self._extract_total(data)

    def get_summary(self, cloud_id: str | None = None, *, force_refresh: bool = False) -> dict[str, Any]:
        cloud_id_value = _to_text(cloud_id or self.config.default_cloud_id)
        if not cloud_id_value:
            raise JumpServerAPIError("未提供 cloud_id，无法统计堡垒机摘要数据", status_code=400)

        cache_key = self._summary_cache_key(cloud_id_value)
        if not force_refresh:
            cached = cache_get(cache_key)
            if isinstance(cached, dict):
                return cached

        hosts = self.list_hosts(cloud_id=cloud_id_value, force_refresh=force_refresh)
        total_hosts = len(hosts)
        explicit_online = [host for host in hosts if isinstance(host.get("online"), bool)]
        if explicit_online:
            online_hosts = sum(1 for host in explicit_online if host.get("online"))
        else:
            online_hosts = total_hosts

        credential_total = sum(
            host.get("credentialCount", 0)
            for host in hosts
            if isinstance(host.get("credentialCount"), int)
        )
        remote_credential_total = self.count_credentials()
        if remote_credential_total is not None:
            credential_total = remote_credential_total if remote_credential_total > 0 else credential_total

        summary = {
            "cloud_id": cloud_id_value,
            "total_hosts": total_hosts,
            "online_hosts": online_hosts,
            "online_users": self.count_online_users(),
            "total_users": self.count_users(),
            "total_credentials": credential_total if credential_total > 0 else None,
        }
        cache_set(cache_key, summary, timeout=self.config.summary_cache_ttl)
        return summary

    def get_oauth_login_url(
        self,
        *,
        user_id: str | None = None,
        team_id: str | None = None,
        page: str | None = None,
        oneoff: bool = False,
        expire_seconds: int | None = None,
    ) -> str:
        user_id_value = _to_text(user_id or self.config.default_user_id)
        team_id_value = _to_text(team_id or self.config.default_team_id)
        if not user_id_value:
            raise JumpServerAPIError("未配置默认 user_id，无法免登录", status_code=400)
        if not team_id_value:
            raise JumpServerAPIError("未配置默认 team_id，无法免登录", status_code=400)

        data = self._request(
            "GET",
            "/oauthLogin",
            params={
                "userId": user_id_value,
                "oneoff": "true" if oneoff else "false",
                "expireSeconds": int(expire_seconds or self.config.oauth_expire_seconds),
                "teamId": team_id_value,
                "page": _to_text(page or self.config.default_page) or "Home",
            },
            expected_statuses=(200,),
        )

        url = _to_text(data.get("url")) if isinstance(data, dict) else ""
        if not url:
            raise JumpServerAPIError("JumpServer 免登录 URL 为空", status_code=502)
        return url

    def restart_host(self, host_id: str, *, force: bool = True) -> None:
        host_id_value = _to_text(host_id)
        if not host_id_value:
            raise JumpServerAPIError("host_id 不能为空", status_code=400)
        self._request(
            "POST",
            f"/host/{host_id_value}/restart",
            params={"force": "true" if force else "false"},
            expected_statuses=(200, 204),
        )

    def delete_host(self, host_id: str) -> None:
        host_id_value = _to_text(host_id)
        if not host_id_value:
            raise JumpServerAPIError("host_id 不能为空", status_code=400)
        self._request("DELETE", f"/host/{host_id_value}", expected_statuses=(200, 204))

    def get_user_info(self, account: str) -> dict[str, Any]:
        account_value = _to_text(account)
        if not account_value:
            raise JumpServerAPIError("account 不能为空", status_code=400)
        data = self._request("GET", f"/user/byAccount/{account_value}", expected_statuses=(200,))
        return data if isinstance(data, dict) else {"data": data}

    def modify_credential_password(self, credential_id: str, password: str) -> None:
        credential_id_value = _to_text(credential_id)
        if not credential_id_value or not password:
            raise JumpServerAPIError("credential_id 和 password 不能为空", status_code=400)
        self._request(
            "POST",
            "/credential/modifyCredentialPass",
            json_body={"credentialIds": credential_id_value, "password": password},
            expected_statuses=(200,),
        )

    def ping(self) -> dict[str, Any]:
        data = self._request("GET", "/ping", expected_statuses=(200,))
        return data if isinstance(data, dict) else {"data": data}

    def add_user_auth(self, host_id: str, user_id: str) -> None:
        host_id_value = _to_text(host_id)
        user_id_value = _to_text(user_id)
        if not host_id_value or not user_id_value:
            raise JumpServerAPIError("host_id 和 user_id 不能为空", status_code=400)
        self._request(
            "POST",
            f"/hostUserAuth/{host_id_value}",
            json_body={"userId": user_id_value},
            expected_statuses=(200,),
        )


def extract_first_credential_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("credentialId", "credential_id"):
            candidate = _to_text(payload.get(key))
            if candidate:
                return candidate

        for key in ("id",):
            candidate = _to_text(payload.get(key))
            if candidate and "credential" in " ".join(payload.keys()).lower():
                return candidate

        for key in ("credential", "credentials", "items", "list", "data", "rows"):
            if key in payload:
                candidate = extract_first_credential_id(payload.get(key))
                if candidate:
                    return candidate

        for value in payload.values():
            candidate = extract_first_credential_id(value)
            if candidate:
                return candidate

    if isinstance(payload, list):
        for item in payload:
            candidate = extract_first_credential_id(item)
            if candidate:
                return candidate
    return ""


def extract_user_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("userId", "user_id", "id"):
            candidate = _to_text(payload.get(key))
            if candidate:
                return candidate
        for value in payload.values():
            candidate = extract_user_id(value)
            if candidate:
                return candidate
    if isinstance(payload, list):
        for item in payload:
            candidate = extract_user_id(item)
            if candidate:
                return candidate
    return ""


def get_jumpserver_client() -> JumpServerClient:
    return JumpServerClient()



