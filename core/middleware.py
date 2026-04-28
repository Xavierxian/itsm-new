from uuid import uuid4

from asgiref.local import Local
from django.utils.deprecation import MiddlewareMixin

_state = Local()


def get_current_user():
    return getattr(_state, "user", None)


def get_request_trace_id():
    return getattr(_state, "trace_id", "")


class RequestContextMiddleware(MiddlewareMixin):
    def process_request(self, request):
        _state.trace_id = uuid4().hex
        _state.user = getattr(request, "user", None)
        request.trace_id = _state.trace_id

    def process_view(self, request, view_func, view_args, view_kwargs):
        _state.user = getattr(request, "user", None)
        return None

    def process_response(self, request, response):
        response["X-Request-ID"] = getattr(request, "trace_id", get_request_trace_id())
        _state.user = None
        _state.trace_id = ""
        return response

    def process_exception(self, request, exception):
        _state.user = None
        _state.trace_id = ""
        return None


class SecurityHeadersMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        response.setdefault("X-Frame-Options", "DENY")
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return response
