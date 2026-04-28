import re
import socket
from ipaddress import ip_address
from urllib import request as urllib_request

from core.cache_helpers import cache_get, cache_set

ACCESS_IP_CACHE_KEY = "core:network:access_ips"
ACCESS_IP_CACHE_TTL = 300


def get_private_ip():
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "-"
    finally:
        if sock is not None:
            sock.close()


def derive_node_label(location_text):
    if not location_text:
        return "-"

    tokens = [token for token in location_text.split() if token]
    if not tokens:
        return "-"

    if tokens[0] == "中国":
        area = "-"
        if len(tokens) >= 3 and tokens[2] != tokens[1]:
            area = tokens[2]
        elif len(tokens) >= 2:
            area = tokens[1]
        return f"{area} / CN"

    if len(tokens) >= 2:
        return f"{tokens[1]} / {tokens[0]}"

    return tokens[0]


def fetch_public_access_info():
    try:
        with urllib_request.urlopen("https://myip.ipip.net", timeout=1.5) as response:
            payload = response.read().decode("utf-8", errors="ignore").strip()
            ip_match = re.search(r"((?:\d{1,3}\.){3}\d{1,3})", payload)
            if ip_match:
                public_ip = ip_match.group(1)
                words = re.findall(r"[\u4e00-\u9fff]+", payload)
                location_words = words[2:] if len(words) > 2 else []
                location_text = " ".join(location_words)
                return public_ip, derive_node_label(location_text)
    except Exception:
        pass

    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib_request.urlopen(url, timeout=1.5) as response:
                payload = response.read().decode("utf-8", errors="ignore").strip()
                match = re.search(r"((?:\d{1,3}\.){3}\d{1,3})", payload)
                if match:
                    return match.group(1), "-"
                if payload:
                    return payload.split()[0].strip(), "-"
        except Exception:
            continue
    return "-", "-"


def get_access_ips():
    cached = cache_get(ACCESS_IP_CACHE_KEY)
    if isinstance(cached, dict):
        private_ip = str(cached.get("private_ip") or "-")
        public_ip = str(cached.get("public_ip") or "-")
        current_node = str(cached.get("current_node") or "-")
        return private_ip, public_ip, current_node

    private_ip = get_private_ip()
    public_ip, current_node = fetch_public_access_info()
    payload = {
        "private_ip": private_ip or "-",
        "public_ip": public_ip or "-",
        "current_node": current_node or "-",
    }
    cache_set(ACCESS_IP_CACHE_KEY, payload, timeout=ACCESS_IP_CACHE_TTL)
    return payload["private_ip"], payload["public_ip"], payload["current_node"]


def _normalize_ip_token(value):
    token = str(value or "").strip()
    if not token:
        return ""
    if token.startswith("[") and "]" in token:
        token = token[1 : token.index("]")]
    if token.count(":") == 1 and "." in token:
        token = token.split(":", 1)[0]
    lowered = token.lower()
    if lowered in {"unknown", "none", "null", "-"}:
        return ""
    return token


def _is_private_or_local(ip_text):
    try:
        parsed = ip_address(ip_text)
    except ValueError:
        return False
    return (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_multicast
    )


def _is_public_ip(ip_text):
    try:
        parsed = ip_address(ip_text)
    except ValueError:
        return False
    return bool(parsed.is_global)


def split_private_public_ips(ip_text):
    normalized = _normalize_ip_token(ip_text)
    if not normalized:
        return "-", "-"
    if _is_public_ip(normalized):
        return "-", normalized
    if _is_private_or_local(normalized):
        return normalized, "-"
    return "-", "-"


def get_request_ip_chain(request):
    if request is None:
        return []

    chain = []
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        for part in forwarded.split(","):
            token = _normalize_ip_token(part)
            if token:
                chain.append(token)

    for header in ("HTTP_X_REAL_IP", "HTTP_CF_CONNECTING_IP", "REMOTE_ADDR"):
        token = _normalize_ip_token(request.META.get(header, ""))
        if token:
            chain.append(token)

    # Keep order while de-duplicating.
    deduped = []
    seen = set()
    for token in chain:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def get_request_client_ip(request):
    chain = get_request_ip_chain(request)
    if chain:
        return chain[0]
    return "-"


def get_request_access_ips(request):
    chain = get_request_ip_chain(request)
    if not chain:
        return "-", "-", "-"

    private_ip = "-"
    public_ip = "-"

    for candidate in chain:
        if private_ip == "-" and _is_private_or_local(candidate):
            private_ip = candidate
        if public_ip == "-" and _is_public_ip(candidate):
            public_ip = candidate
        if private_ip != "-" and public_ip != "-":
            break

    current_node = public_ip if public_ip != "-" else private_ip
    return private_ip, public_ip, current_node
