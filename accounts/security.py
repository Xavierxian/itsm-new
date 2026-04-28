from django.conf import settings
from core.cache_helpers import cache_add, cache_delete_many, cache_get, cache_incr, cache_set


def _normalize_username(username):
    return str(username or "").strip().lower()


def _normalize_ip(ip_address):
    return str(ip_address or "").strip().lower()


def user_failure_key(username):
    return f"auth:fail:{_normalize_username(username)}"


def ip_rate_limit_key(ip_address):
    return f"auth:rl:ip:{_normalize_ip(ip_address)}"


def ip_user_rate_limit_key(ip_address, username):
    return f"auth:rl:ipu:{_normalize_ip(ip_address)}:{_normalize_username(username)}"


def _incr_with_ttl(key, ttl):
    next_value = cache_incr(key)
    if next_value is not None:
        return int(next_value)

    # Atomic create-once path for first write in a TTL window.
    if cache_add(key, 1, timeout=ttl):
        return 1

    # If another concurrent request won the add race, retry atomic increment.
    next_value = cache_incr(key)
    if next_value is not None:
        return int(next_value)

    current = cache_get(key)
    try:
        fallback = int(current) + 1
    except (ValueError, TypeError):
        fallback = 1
    if cache_set(key, fallback, timeout=ttl):
        return fallback
    return int(current) if str(current).isdigit() else 0


def get_login_limits():
    window = int(getattr(settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 600))
    return {
        "window": max(60, window),
        "per_ip": int(getattr(settings, "LOGIN_RATE_LIMIT_PER_IP", 60)),
        "per_ip_user": int(getattr(settings, "LOGIN_RATE_LIMIT_PER_IP_USER", 10)),
    }


def is_login_rate_limited(username, ip_address):
    limits = get_login_limits()
    user_ip_count = int(cache_get(ip_user_rate_limit_key(ip_address, username), 0) or 0)
    ip_count = int(cache_get(ip_rate_limit_key(ip_address), 0) or 0)
    return user_ip_count >= limits["per_ip_user"] or ip_count >= limits["per_ip"]


def register_login_failure(username, ip_address):
    limits = get_login_limits()
    user_key = user_failure_key(username)
    ip_key = ip_rate_limit_key(ip_address)
    ip_user_key = ip_user_rate_limit_key(ip_address, username)
    user_count = _incr_with_ttl(user_key, ttl=limits["window"])
    ip_count = _incr_with_ttl(ip_key, ttl=limits["window"])
    ip_user_count = _incr_with_ttl(ip_user_key, ttl=limits["window"])
    return {
        "user_count": user_count,
        "ip_count": ip_count,
        "ip_user_count": ip_user_count,
    }


def reset_login_failures(username, ip_address=None):
    keys = [user_failure_key(username)]
    if ip_address:
        keys.append(ip_user_rate_limit_key(ip_address, username))
    cache_delete_many(keys)
