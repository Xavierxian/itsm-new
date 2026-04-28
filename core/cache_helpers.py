import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def _warn(action, key, exc):
    logger.warning("Cache %s failed for key=%s: %s", action, key, exc)


def _is_expected_incr_miss(exc):
    text = str(exc or "").strip().lower()
    return "not found" in text or "does not exist" in text


def cache_get(key, default=None):
    try:
        return cache.get(key, default)
    except Exception as exc:
        _warn("get", key, exc)
        return default


def cache_set(key, value, timeout=None):
    try:
        cache.set(key, value, timeout=timeout)
        return True
    except Exception as exc:
        _warn("set", key, exc)
        return False


def cache_add(key, value, timeout=None):
    try:
        return bool(cache.add(key, value, timeout=timeout))
    except Exception as exc:
        _warn("add", key, exc)
        return False


def cache_delete(key):
    try:
        cache.delete(key)
        return True
    except Exception as exc:
        _warn("delete", key, exc)
        return False


def cache_delete_many(keys):
    try:
        cache.delete_many(keys)
        return True
    except Exception as exc:
        _warn("delete_many", ",".join(str(item) for item in keys), exc)
        return False


def cache_incr(key, delta=1):
    try:
        return int(cache.incr(key, delta))
    except Exception as exc:
        if _is_expected_incr_miss(exc):
            return None
        _warn("incr", key, exc)
        return None
