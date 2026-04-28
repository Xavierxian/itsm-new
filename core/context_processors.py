from core.navigation import NAVIGATION
from core.network import get_access_ips


def _is_visible(user, item):
    permission = item.get("permission")
    if not permission:
        return True
    return user.is_authenticated and (user.is_superuser or user.has_perm(permission))


def _is_active(item, current_view):
    url = item.get("url")
    if not url or not current_view:
        return False

    if current_view == url:
        return True

    if ":" not in url or "-" not in url:
        return False

    namespace, name = url.split(":", 1)
    stem, suffix = name.rsplit("-", 1)
    if suffix != "list":
        return False

    return current_view.startswith(f"{namespace}:{stem}-")


def _filter_items(user, items):
    filtered = []
    for item in items:
        children = item.get("children")
        if children:
            visible_children = []
            for child in children:
                if not _is_visible(user, child):
                    continue
                visible_children.append({**child, "is_active": False})
            if visible_children:
                filtered.append({**item, "children": visible_children, "is_active": False})
        elif _is_visible(user, item):
            filtered.append({**item, "is_active": False})
    return filtered


def navigation(request):
    current_view = getattr(request.resolver_match, "view_name", "")
    navigation_items = _filter_items(request.user, NAVIGATION)
    private_ip, public_ip, current_node = get_access_ips()

    for item in navigation_items:
        children = item.get("children")
        if children:
            # Prefer exact match in the same group (e.g. authorization-detail),
            # then fall back to stem-based list matching.
            exact_matches = [child for child in children if current_view and child.get("url") == current_view]
            if exact_matches:
                active_claimed = False
                for child in children:
                    child_active = (child.get("url") == current_view) and not active_claimed
                    child["is_active"] = child_active
                    if child_active:
                        active_claimed = True
                item["is_active"] = any(child["is_active"] for child in children)
                continue

            child_is_active = False
            active_claimed = False
            for child in children:
                child_active = _is_active(child, current_view)
                if child_active and active_claimed:
                    child_active = False
                child["is_active"] = child_active
                if child_active:
                    active_claimed = True
                child_is_active = child_is_active or child["is_active"]
            item["is_active"] = child_is_active
        else:
            item["is_active"] = _is_active(item, current_view)

    return {
        "navigation_items": navigation_items,
        "sidebar_current_node": current_node,
        "sidebar_private_ip": private_ip,
        "sidebar_public_ip": public_ip,
    }
