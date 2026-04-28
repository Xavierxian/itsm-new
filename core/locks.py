from contextlib import contextmanager
from uuid import uuid4

from core.cache_helpers import cache_add, cache_delete, cache_get


@contextmanager
def cache_lock(name, timeout=300):
    key = f"lock:task:{name}"
    token = uuid4().hex
    acquired = cache_add(key, token, timeout=timeout)
    try:
        yield acquired
    finally:
        if not acquired:
            return
        current = cache_get(key)
        if current == token:
            cache_delete(key)
