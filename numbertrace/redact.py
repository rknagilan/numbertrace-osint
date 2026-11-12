"""Redaction helpers so phone numbers never reach logs or error telemetry."""

from __future__ import annotations

import logging
import re

# A run of 6+ digits, optionally separated by spaces, dots, dashes or brackets.
_PHONEISH = re.compile(r"\+?\(?\d(?:[\d\s().-]{4,}\d)")


def mask_number(value: str) -> str:
    """Mask all but the last two digits: '+94771234567' -> '+94*******67'."""
    digits = [c for c in value if c.isdigit()]
    if len(digits) < 6:
        return value
    keep_prefix = 2 if value.strip().startswith("+") else 0
    out: list[str] = []
    seen = 0
    total = len(digits)
    for ch in value:
        if ch.isdigit():
            seen += 1
            if seen <= keep_prefix or seen > total - 2:
                out.append(ch)
            else:
                out.append("*")
        else:
            out.append(ch)
    return "".join(out)


def redact_text(text: str) -> str:
    """Replace every phone-like sequence in free text with a masked version."""

    def _sub(match: re.Match[str]) -> str:
        chunk = match.group(0)
        if sum(c.isdigit() for c in chunk) < 6:
            return chunk
        return mask_number(chunk)

    return _PHONEISH.sub(_sub, text)


class RedactingFilter(logging.Filter):
    """Logging filter that masks phone-like data in messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact_text(str(v)) for k, v in record.args.items()}
            else:
                record.args = tuple(redact_text(str(a)) for a in record.args)
        return True


def configure_logging(level: int = logging.WARNING) -> logging.Logger:
    logger = logging.getLogger("numbertrace")
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.addFilter(RedactingFilter())
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
