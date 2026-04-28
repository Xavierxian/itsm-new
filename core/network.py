import re
import socket
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
