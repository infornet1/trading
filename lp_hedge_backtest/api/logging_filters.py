"""Logging filters to prevent sensitive values from leaking into access logs."""

import logging
import re

# Redact JWT tokens passed as WebSocket query parameters, e.g. /ws/17?token=eyJ...
_TOKEN_REDACT_RE = re.compile(r"([?&]token=)[^&\s]+")


def _redact(value):
    if isinstance(value, str):
        return _TOKEN_REDACT_RE.sub(r"\1***", value)
    return value


class TokenRedactFilter(logging.Filter):
    """Redact `token=...` from log messages and arguments."""

    def filter(self, record):
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_redact(a) for a in record.args)
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        return True


def install_token_redaction():
    """Attach the token-redaction filter to uvicorn loggers."""
    filt = TokenRedactFilter()
    for name in ("uvicorn.access", "uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, TokenRedactFilter) for f in logger.filters):
            logger.addFilter(filt)
