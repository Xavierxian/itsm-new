import logging

from core.security import redact_text


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        try:
            rendered = record.getMessage()
            record.msg = redact_text(rendered)
            record.args = ()
        except Exception:
            pass
        return True
